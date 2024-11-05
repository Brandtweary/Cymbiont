{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = with pkgs; [
    (python39.withPackages(ps: with ps; [
      pip
      virtualenv
    ]))
  ];

  shellHook = ''
    echo ""
    echo -e "\033[32m╔════════════════════════════════════════╗\033[0m"
    echo -e "\033[32m║        Initializing \033[34mCyberOrganism\033[32m      ║\033[0m"
    echo -e "\033[32m╚════════════════════════════════════════╝\033[0m"
    echo -e "\033[32m>> Runtime: \033[34mPython $(python --version 2>&1 | cut -d' ' -f2)\033[0m"
    echo -e "\033[32m>> Environment: Development\033[0m"
    
    # Check internet connectivity
    if ping -c 1 8.8.8.8 >/dev/null 2>&1; then
        echo -e "\033[32m>> Network Status: \033[32mOnline\033[0m"
    else
        echo -e "\033[32m>> Network Status: \033[31mOffline\033[0m"
        echo -e "\033[31m>> Warning: Internet connection required \033[0m"
    fi
    
    echo ""
  '';
}