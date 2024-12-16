#!/bin/bash

# Debug mode (set to true to enable debug output)
DEBUG=false

# Function to show progress
progress() {
    local current="$1"
    local total="$2"
    local width=50
    local percentage=$((current * 100 / total))
    local completed=$((width * current / total))
    printf "\r[%-${width}s] %d%%" "$(printf '#%.0s' $(seq 1 $completed))" "$percentage"
}

# Function to start a new progress bar
start_progress() {
    printf "\r%-100s" " "  # Clear line once at the start
}

# Function to complete a progress bar
complete_progress_bar() {
    progress "" "$1" "$1"
    echo
}

# Function to handle errors
error_exit() {
    echo "Error: $1" >&2
    exit 1
}

# Function for debug logging
debug() {
    if [ "$DEBUG" = true ]; then
        echo "[DEBUG] $1" >&2
    fi
}

# Function to process directory contents recursively
process_directory_contents() {
    local dir="$1"
    
    # Set directory permissions recursively (for level 3 and deeper)
    find "$dir" -mindepth 1 -type d ! -type l -exec chmod 2750 {} \;
    
    # Set file permissions recursively (for all files under this directory)
    find "$dir" -type f ! -type l -exec chmod 640 {} \;
    
    # Set group ownership recursively
    find "$dir" -exec chgrp "$PROJECT_GROUP" {} \;
    
    # Set ACLs recursively
    find "$dir" -mindepth 1 -type d ! -type l -exec setfacl -m g:$PROJECT_GROUP:r-x {} \; -exec setfacl -d -m g:$PROJECT_GROUP:r-X {} \;
    find "$dir" -mindepth 1 -type d ! -type l -exec setfacl -m u:$PROJECT_WRITE_EXECUTE:rwx {} \; -exec setfacl -d -m u:$PROJECT_WRITE_EXECUTE:rwx {} \;
    find "$dir" -type f ! -type l -exec setfacl -m g:$PROJECT_GROUP:r-- {} \; -exec setfacl -m u:$PROJECT_WRITE_EXECUTE:rw- {} \;
    
    # Special handling for agent workspace
    if [[ "$(realpath "$dir")" == "$(realpath "$AGENT_WORKSPACE_DIR")"* ]]; then
        # Set ACLs for directories
        find "$dir" -mindepth 1 -type d ! -type l -exec setfacl -m u:$PROJECT_RESTRICTED_WRITE:rwx {} \; -exec setfacl -d -m u:$PROJECT_RESTRICTED_WRITE:rwx {} \;
        # Set ACLs for files
        find "$dir" -type f ! -type l -exec setfacl -m u:$PROJECT_RESTRICTED_WRITE:rw- {} \;
        # Set default ACL for files on the agent workspace dir itself
        setfacl -d -m u:$PROJECT_RESTRICTED_WRITE:rw- "$AGENT_WORKSPACE_DIR"
    fi
}

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    error_exit "This script must be run as root"
fi

# Check for ACL support and install if needed
if ! command -v setfacl &> /dev/null; then
    echo "ACL support not found. Installing acl package..."
    if [ -f /etc/debian_version ]; then
        debug "Detected Debian/Ubuntu system"
        apt-get update && apt-get install -y acl || error_exit "Failed to install acl package"
    elif [ -f /etc/redhat-release ]; then
        debug "Detected RHEL/CentOS system"
        yum install -y acl || error_exit "Failed to install acl package"
    elif [ -f /etc/arch-release ]; then
        debug "Detected Arch Linux system"
        pacman -S --noconfirm acl || error_exit "Failed to install acl package"
    else
        error_exit "Unsupported distribution. Please install 'acl' package manually"
    fi
fi

# Check for other required tools
for cmd in find; do
    if ! command -v "$cmd" &> /dev/null; then
        error_exit "Required command not found: $cmd"
    fi
done

# Check if filesystem supports ACLs
if ! mount | grep -q "acl"; then
    echo "Enabling ACLs on Cymbiont filesystem..."
    mount -o remount,acl / || error_exit "Failed to enable ACLs on Cymbiont filesystem"
    if [ -f /etc/fstab ]; then
        sed -i 's/\([[:space:]]\+defaults\)/\1,acl/' /etc/fstab || error_exit "Failed to update fstab"
    fi
fi

# User names for different access tiers
PROJECT_READ="cymbiont_project_read"                    # Tier 1: Project-only read access
SYSTEM_READ="cymbiont_system_read"                      # Tier 2: System-wide read access
PROJECT_RESTRICTED_WRITE="cymbiont_project_restr_write" # Tier 3: System read + agent workspace write
PROJECT_WRITE_EXECUTE="cymbiont_project_write_exec"     # Tier 4: Project read/write/execute
PROJECT_GROUP="cymbiont_project"                        # Group for project access

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_WORKSPACE_DIR="$PROJECT_ROOT/data/agent_workspace"

echo "Setting up restricted users and groups..."

# Create project access group and users (fast operation)
if ! getent group "$PROJECT_GROUP" >/dev/null 2>&1; then
    debug "Creating project access group $PROJECT_GROUP"
    groupadd "$PROJECT_GROUP" || error_exit "Failed to create group $PROJECT_GROUP"
    echo "Created project access group: $PROJECT_GROUP"
fi

# Create all restricted users (fast operation)
for user in "$PROJECT_READ" "$SYSTEM_READ" "$PROJECT_RESTRICTED_WRITE" "$PROJECT_WRITE_EXECUTE"; do
    if ! id -u "$user" >/dev/null 2>&1; then
        debug "Creating user $user"
        if [ "$user" = "$PROJECT_READ" ]; then
            useradd -r -M -s /bin/bash -G "$PROJECT_GROUP" "$user" || error_exit "Failed to create user $user"
        else
            useradd -r -M -s /bin/bash "$user" || error_exit "Failed to create user $user"
        fi
        echo "Created user: $user"
    fi
done

# Get the current user (the one who invoked sudo)
SUDO_USER="${SUDO_USER:-$USER}"

echo "Setting up project directory permissions..."

# Reset base ACLs on project root
debug "Setting base permissions on project root"
setfacl -b "$PROJECT_ROOT" || error_exit "Failed to reset ACLs on $PROJECT_ROOT"
chown "$SUDO_USER:$PROJECT_GROUP" "$PROJECT_ROOT" || error_exit "Failed to set ownership on $PROJECT_ROOT"
chmod 2750 "$PROJECT_ROOT" || error_exit "Failed to set permissions on $PROJECT_ROOT"

# Set default ACLs on project root
setfacl -m g:$PROJECT_GROUP:r-x "$PROJECT_ROOT" || error_exit "Failed to set group ACL on $PROJECT_ROOT"
setfacl -d -m g:$PROJECT_GROUP:r-X "$PROJECT_ROOT" || error_exit "Failed to set default group ACL on $PROJECT_ROOT"
setfacl -m u:$PROJECT_WRITE_EXECUTE:rwx "$PROJECT_ROOT" || error_exit "Failed to set write-execute ACL on $PROJECT_ROOT"
setfacl -d -m u:$PROJECT_WRITE_EXECUTE:rwx "$PROJECT_ROOT" || error_exit "Failed to set default write-execute ACL on $PROJECT_ROOT"

# Process Cymbiont files
echo "Processing Cymbiont files..."
total_files=$(find "$PROJECT_ROOT" -mindepth 1 -maxdepth 1 -type f ! -type l | wc -l)
current=0
start_progress

while IFS= read -r -d '' file; do
    ((current++))
    progress "$current" "$total_files"
    
    if [ ! -L "$file" ]; then
        debug "Setting file permissions for $file"
        chown "$SUDO_USER:$PROJECT_GROUP" "$file" || error_exit "Failed to set ownership on $file"
        chmod 640 "$file" || error_exit "Failed to set permissions on $file"
        setfacl -m g:$PROJECT_GROUP:r-- "$file" || error_exit "Failed to set ACLs on $file"
        setfacl -m u:$PROJECT_WRITE_EXECUTE:rw- "$file" || error_exit "Failed to set write-execute ACLs"
    fi
done < <(find "$PROJECT_ROOT" -mindepth 1 -maxdepth 1 -type f ! -type l -print0)
echo  # New line after progress bar

# Process directories
echo "Processing directories..."
while IFS= read -r -d '' dir; do
    if [ ! -L "$dir" ]; then
        dir_name=$(basename "$dir")
        echo "Processing $dir_name..."
        
        # Set ownership for the entire directory tree
        chown -R "$SUDO_USER:$PROJECT_GROUP" "$dir" || error_exit "Failed to set ownership on $dir"
        
        # Set permissions and ACLs for this directory
        chmod 2750 "$dir"
        setfacl -m g:$PROJECT_GROUP:r-x "$dir"
        setfacl -d -m g:$PROJECT_GROUP:r-X "$dir"
        setfacl -m u:$PROJECT_WRITE_EXECUTE:rwx "$dir"
        setfacl -d -m u:$PROJECT_WRITE_EXECUTE:rwx "$dir"
        
        # Special handling for agent workspace
        if [[ "$(realpath "$dir")" == "$(realpath "$AGENT_WORKSPACE_DIR")"* ]]; then
            setfacl -m u:$PROJECT_RESTRICTED_WRITE:rwx "$dir"
            setfacl -d -m u:$PROJECT_RESTRICTED_WRITE:rwx "$dir"
        fi
        
        # Count total items to process
        total_items=$(find "$dir" -mindepth 1 \( -type f -o -type d \) ! -type l | wc -l)
        current=0
        start_progress
        
        # Process all files
        while IFS= read -r -d '' file; do
            ((current++))
            progress "$current" "$total_items"
            
            chmod 640 "$file"
            setfacl -m g:$PROJECT_GROUP:r-- "$file"
            setfacl -m u:$PROJECT_WRITE_EXECUTE:rw- "$file"
            
            if [[ "$(realpath "$file")" == "$(realpath "$AGENT_WORKSPACE_DIR")"* ]]; then
                setfacl -m u:$PROJECT_RESTRICTED_WRITE:rw- "$file"
            fi
        done < <(find "$dir" -mindepth 1 -type f ! -type l -print0)
        
        # Process all subdirectories
        while IFS= read -r -d '' subdir; do
            ((current++))
            progress "$current" "$total_items"
            
            chmod 2750 "$subdir"
            setfacl -m g:$PROJECT_GROUP:r-x "$subdir"
            setfacl -d -m g:$PROJECT_GROUP:r-X "$subdir"
            setfacl -m u:$PROJECT_WRITE_EXECUTE:rwx "$subdir"
            setfacl -d -m u:$PROJECT_WRITE_EXECUTE:rwx "$subdir"
            
            if [[ "$(realpath "$subdir")" == "$(realpath "$AGENT_WORKSPACE_DIR")"* ]]; then
                setfacl -m u:$PROJECT_RESTRICTED_WRITE:rwx "$subdir"
                setfacl -d -m u:$PROJECT_RESTRICTED_WRITE:rwx "$subdir"
            fi
        done < <(find "$dir" -mindepth 1 -type d ! -type l -print0)
        echo  # New line after progress bar
    fi
done < <(find "$PROJECT_ROOT" -mindepth 1 -maxdepth 1 -type d ! -type l -print0)

# Set up user profiles (fast operations)
echo "Setting up user profiles..."
for user in "$PROJECT_READ" "$SYSTEM_READ" "$PROJECT_RESTRICTED_WRITE" "$PROJECT_WRITE_EXECUTE"; do
    debug "Creating profile for $user"
    profile="/etc/profile.d/cymbiont_${user}.sh"
    echo "umask 0027" > "$profile" || error_exit "Failed to create profile for $user"
    chown "root:$user" "$profile" || error_exit "Failed to set ownership on profile for $user"
    chmod 440 "$profile" || error_exit "Failed to set permissions on profile for $user"
done

# Set up mount restrictions (fast operation)
echo "Setting up mount restrictions..."
debug "Creating namespace configuration"
cat > /etc/security/namespace.conf << EOF || error_exit "Failed to create namespace.conf"
/home/$PROJECT_READ    /    /home/$PROJECT_READ    bind
/home/$SYSTEM_READ    /    /home/$SYSTEM_READ    bind
EOF

echo "Setup complete! Created users:"
echo "- $PROJECT_READ: Project read-only access"
echo "- $SYSTEM_READ: System-wide read access"
echo "- $PROJECT_RESTRICTED_WRITE: System read + agent workspace write"
echo "- $PROJECT_WRITE_EXECUTE: Project read/write/execute"
