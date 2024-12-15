#!/bin/bash
set -e
set -x  # Enable debug output

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "This script must be run as root"
    exit 1
fi

# Check for ACL support and enable it on the filesystem
if ! command -v setfacl &> /dev/null; then
    echo "ACL support not found. Please install acl package first:"
    echo "sudo apt-get install acl  # For Debian/Ubuntu"
    echo "sudo yum install acl      # For RHEL/CentOS"
    echo "sudo pacman -S acl        # For Arch Linux"
    exit 1
fi

# Check if filesystem supports ACLs
if ! mount | grep -q "acl"; then
    echo "Enabling ACLs on root filesystem..."
    mount -o remount,acl /
    # Make ACL support persistent
    if [ -f /etc/fstab ]; then
        # Add acl option to root partition if not present
        sed -i 's/\([[:space:]]\+defaults\)/\1,acl/' /etc/fstab
    fi
fi

# User names for different access tiers
PROJECT_READ="cymbiont_project_read"                    # Tier 1: Project-only read access
SYSTEM_READ="cymbiont_system_read"                      # Tier 2: System-wide read access
PROJECT_RESTRICTED_WRITE="cymbiont_project_restr_write" # Tier 3: System read + agent_workspace write
PROJECT_WRITE_EXECUTE="cymbiont_project_write_exec"     # Tier 4: Project read/write/execute
PROJECT_GROUP="cymbiont_project"                        # Group for project access

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENT_WORKSPACE_DIR="$PROJECT_ROOT/data/agent_workspace"

echo "Setting up restricted users and groups..."

# Create project access group (for tier 1 only)
if ! getent group "$PROJECT_GROUP" >/dev/null 2>&1; then
    groupadd "$PROJECT_GROUP"
    echo "Created project access group: $PROJECT_GROUP"
fi

# Create project-read user (tier 1 - most restricted)
if ! id -u "$PROJECT_READ" >/dev/null 2>&1; then
    useradd -r -M -s /bin/bash -G "$PROJECT_GROUP" "$PROJECT_READ"
    echo "Created project-read user: $PROJECT_READ"
fi

# Create system-read user (tier 2)
if ! id -u "$SYSTEM_READ" >/dev/null 2>&1; then
    useradd -r -M -s /bin/bash "$SYSTEM_READ"
    echo "Created system-read user: $SYSTEM_READ"
fi

# Create project-restricted-write user (tier 3)
if ! id -u "$PROJECT_RESTRICTED_WRITE" >/dev/null 2>&1; then
    useradd -r -M -s /bin/bash "$PROJECT_RESTRICTED_WRITE"
    echo "Created project-restricted-write user: $PROJECT_RESTRICTED_WRITE"
fi

# Create project-write-execute user (tier 4)
if ! id -u "$PROJECT_WRITE_EXECUTE" >/dev/null 2>&1; then
    useradd -r -M -s /bin/bash "$PROJECT_WRITE_EXECUTE"
    echo "Created project-write-execute user: $PROJECT_WRITE_EXECUTE"
fi

# Get the current user (the one who invoked sudo)
SUDO_USER="${SUDO_USER:-$USER}"

# Set up project directory permissions with ACLs
echo "Setting up project directory permissions..."

# Reset ACLs
setfacl -R -b "$PROJECT_ROOT"

# Set base permissions (more restrictive than before)
chown -R "$SUDO_USER:$PROJECT_GROUP" "$PROJECT_ROOT"
chmod -R 750 "$PROJECT_ROOT"

# Set default ACLs for new files/directories
setfacl -R -d -m g:$PROJECT_GROUP:r-X "$PROJECT_ROOT"  # Capital X means execute only for directories

# Set ACLs for existing files and directories
find "$PROJECT_ROOT" -type d -exec setfacl -m g:$PROJECT_GROUP:r-x {} \;  # Allow traversing directories
find "$PROJECT_ROOT" -type f -exec setfacl -m g:$PROJECT_GROUP:r-- {} \;  # No execute on files

# Set up ACLs for project_write_execute user (Tier 4)
setfacl -R -m u:$PROJECT_WRITE_EXECUTE:rwx "$PROJECT_ROOT"
setfacl -R -d -m u:$PROJECT_WRITE_EXECUTE:rwx "$PROJECT_ROOT"

# Set up agent workspace directory with special permissions
echo "Setting up agent workspace directory..."
mkdir -p "$AGENT_WORKSPACE_DIR"

# Reset ACLs for agent_workspace
setfacl -R -b "$AGENT_WORKSPACE_DIR"

# Set ownership and base permissions
chown -R "$SUDO_USER:$PROJECT_WRITE_EXECUTE" "$AGENT_WORKSPACE_DIR"
chmod 770 "$AGENT_WORKSPACE_DIR"

# Set specific ACLs for agent_workspace
setfacl -R -d -m u:$PROJECT_WRITE_EXECUTE:rwx "$AGENT_WORKSPACE_DIR"  # Default ACLs for new files
find "$AGENT_WORKSPACE_DIR" -type d -exec setfacl -m u:$PROJECT_WRITE_EXECUTE:rwx {} \;  # Directories
find "$AGENT_WORKSPACE_DIR" -type f -exec setfacl -m u:$PROJECT_WRITE_EXECUTE:rw- {} \;  # Files (no execute)

# Set up ACLs for project_restricted_write user (Tier 3)
setfacl -R -m u:$PROJECT_RESTRICTED_WRITE:r-x "$AGENT_WORKSPACE_DIR"  # Base read + traverse
setfacl -R -d -m u:$PROJECT_RESTRICTED_WRITE:r-x "$AGENT_WORKSPACE_DIR"
find "$AGENT_WORKSPACE_DIR" -type d -exec setfacl -m u:$PROJECT_RESTRICTED_WRITE:rwx {} \;  # Directories
find "$AGENT_WORKSPACE_DIR" -type f -exec setfacl -m u:$PROJECT_RESTRICTED_WRITE:rw- {} \;  # Files (no execute)

# Optional: Set up more restrictive umask for restricted users
for user in "$PROJECT_READ" "$SYSTEM_READ" "$PROJECT_RESTRICTED_WRITE" "$PROJECT_WRITE_EXECUTE"; do
    # Create user-specific bash_profile to set umask
    profile="/etc/profile.d/cymbiont_${user}.sh"
    echo "umask 0027" > "$profile"  # rwxr-x--- for new files
    chown "root:$user" "$profile"
    chmod 440 "$profile"
done

echo "Setup complete. The restricted users have been configured:"
echo "- $PROJECT_READ (tier 1): Read-only access to project files via $PROJECT_GROUP"
echo "  * Can read files and traverse directories"
echo "  * Cannot execute any files"
echo "- $SYSTEM_READ (tier 2): Read-only access to system files"
echo "  * Relies on command validation for execution control"
echo "- $PROJECT_RESTRICTED_WRITE (tier 3): System read + write access to $AGENT_WORKSPACE_DIR"
echo "  * Can read/write but not execute in agent_workspace"
echo "- $PROJECT_WRITE_EXECUTE (tier 4): Project execution access"
echo "  * Can execute files in project directory"
echo ""
echo "To clean up if needed, run:"
echo "sudo userdel $PROJECT_READ"
echo "sudo userdel $SYSTEM_READ"
echo "sudo userdel $PROJECT_RESTRICTED_WRITE"
echo "sudo userdel $PROJECT_WRITE_EXECUTE"
echo "sudo groupdel $PROJECT_GROUP"
echo "sudo rm /etc/profile.d/cymbiont_*.sh"
echo "sudo setfacl -R -b $PROJECT_ROOT  # Remove all ACLs"
