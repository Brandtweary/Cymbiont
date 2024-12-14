if __name__ == "__main__":
    import os
    import sys
    from pathlib import Path
    
    # Get path to cymbiont.py
    project_root = Path(__file__).parent.parent
    cymbiont_path = project_root / 'cymbiont.py'
    
    # Re-run through cymbiont
    os.execv(sys.executable, [sys.executable, str(cymbiont_path), '--test', 'bash_executor'])
else:
    import os
    from pathlib import Path
    from agents.agent_types import ShellAccessTier
    from agents.bash_executor import BashExecutor
    from shared_resources import logger

    async def test_access_tiers():
        """Test shell access tier restrictions."""
        project_root = Path(__file__).parent.parent
        test_file = project_root / "tests" / "test_file.txt"
        protected_file = project_root / "src" / "agents" / "bash_executor.py"
        
        # Test Tier 1: Project Read-Only
        executor = BashExecutor(ShellAccessTier.TIER_1_PROJECT_READ)
        
        # Test write operations are blocked
        write_commands = [
            f"touch {test_file}",  # Create file
            f"mkdir -p {project_root}/test_dir",  # Create directory
            f"echo 'test' > {test_file}",  # Write to file
            f"rm -f {test_file}",  # Delete file
            f"cp {protected_file} {test_file}",  # Copy file
            f"mv {test_file} {test_file}.bak",  # Move/rename file
        ]
        for cmd in write_commands:
            stdout, stderr = executor.execute(cmd)
            assert "Security violation" in stderr, f"TIER_1 should block write operation: {cmd}"
        
        # Test read operations within project
        stdout, stderr = executor.execute(f"cat {protected_file}")
        assert stderr == "", "TIER_1 should allow reading protected files"
        stdout, stderr = executor.execute("ls src/")
        assert stderr == "", "TIER_1 should allow listing project directories"
        
        # Test read operations outside project are blocked
        outside_read_commands = [
            "cat /etc/hosts",  # Read system file
            "ls /etc/",  # List system directory
            "ls /",  # List root
            "cat /proc/cpuinfo",  # Read proc
        ]
        for cmd in outside_read_commands:
            stdout, stderr = executor.execute(cmd)
            assert "Security violation" in stderr, f"TIER_1 should block reading outside project: {cmd}"
        
        # Test navigation restrictions
        # Should block navigation outside project
        outside_nav_commands = [
            "cd /",  # Root
            "cd /tmp",  # System directory
            "cd ..",  # Parent of project
            f"cd {project_root}/../",  # Parent via full path
        ]
        for cmd in outside_nav_commands:
            stdout, stderr = executor.execute(cmd)
            assert "Security violation" in stderr, f"TIER_1 should block navigation outside project: {cmd}"
            
        # Should allow navigation within project
        stdout, stderr = executor.execute(f"cd {project_root}/src")
        assert stderr == "", "TIER_1 should allow navigation within project"
        stdout, stderr = executor.execute("cd ../tests")
        assert stderr == "", "TIER_1 should allow relative navigation within project"
        
        executor.close()

        # Test Tier 2: System-Wide Read
        executor = BashExecutor(ShellAccessTier.TIER_2_SYSTEM_READ)
        
        # Test write operations are blocked
        write_commands = [
            f"touch {test_file}",  # Create file
            f"mkdir -p {project_root}/test_dir",  # Create directory
            f"echo 'test' > {test_file}",  # Write to file
            f"rm -f {test_file}",  # Delete file
            f"cp /etc/hosts {test_file}",  # Copy file
            f"mv {test_file} {test_file}.bak",  # Move/rename file
        ]
        for cmd in write_commands:
            stdout, stderr = executor.execute(cmd)
            assert "Security violation" in stderr, f"TIER_2 should block write operation: {cmd}"
        
        # Test read operations within project
        stdout, stderr = executor.execute(f"cat {protected_file}")
        assert stderr == "", "TIER_2 should allow reading protected files"
        stdout, stderr = executor.execute("ls src/")
        assert stderr == "", "TIER_2 should allow listing project directories"
        
        # Test read operations outside project
        stdout, stderr = executor.execute("cat /etc/hosts")
        assert stderr == "", "TIER_2 should allow reading system files"
        stdout, stderr = executor.execute("ls /etc/")
        assert stderr == "", "TIER_2 should allow listing system directories"
        
        # Test navigation - should be allowed outside project
        stdout, stderr = executor.execute("cd /")
        assert stderr == "", "TIER_2 should allow system-wide navigation"
        stdout, stderr = executor.execute("cd /tmp")
        assert stderr == "", "TIER_2 should allow navigation to system directories"
        stdout, stderr = executor.execute(f"cd {project_root}")
        assert stderr == "", "TIER_2 should allow navigation back to project"
        
        executor.close()

        # Test Tier 3: Project Restricted Write
        executor = BashExecutor(ShellAccessTier.TIER_3_PROJECT_RESTRICTED)
        stdout, stderr = executor.execute(f"touch {test_file}")
        assert stderr == "", "TIER_3 should allow write to non-protected files"
        stdout, stderr = executor.execute(f"touch {protected_file}")
        assert "Security violation" in stderr, "TIER_3 should block writes to protected files"
        
        # Test navigation - should be allowed outside project
        stdout, stderr = executor.execute("cd /")
        assert stderr == "", "TIER_3 should allow system-wide navigation"
        stdout, stderr = executor.execute("cd /tmp")
        assert stderr == "", "TIER_3 should allow navigation to system directories"
        stdout, stderr = executor.execute(f"cd {project_root}")
        assert stderr == "", "TIER_3 should allow navigation back to project"
        
        executor.close()

        # Test Tier 4: Full Project Write
        executor = BashExecutor(ShellAccessTier.TIER_4_PROJECT_WRITE)
        
        # Test write operations within project, including protected files
        stdout, stderr = executor.execute(f"touch {test_file}")
        assert stderr == "", "TIER_4 should allow project writes"
        stdout, stderr = executor.execute(f"mkdir -p {project_root}/test_dir")
        assert stderr == "", "TIER_4 should allow directory creation"
        stdout, stderr = executor.execute(f"echo 'test' > {test_file}")
        assert stderr == "", "TIER_4 should allow file modification"
        
        # Test write access to protected files (should be allowed in tier 4)
        stdout, stderr = executor.execute(f"echo 'test' > {protected_file}.bak")
        assert stderr == "", "TIER_4 should allow writes to protected paths"
        stdout, stderr = executor.execute(f"rm {protected_file}.bak")
        assert stderr == "", "TIER_4 should allow deletion of files in protected paths"
        
        # Test write operations outside project
        stdout, stderr = executor.execute("touch /tmp/test_file")
        assert "Security violation" in stderr, "TIER_4 should block writes outside project"
        
        # Test navigation - should be allowed outside project in Tier 4
        stdout, stderr = executor.execute("cd /")
        assert stderr == "", "TIER_4 should allow navigation outside project"
        stdout, stderr = executor.execute("cd /tmp")
        assert stderr == "", "TIER_4 should allow navigation to system directories"
        stdout, stderr = executor.execute(f"cd {project_root}/test_dir")
        assert stderr == "", "TIER_4 should allow navigation within project"
        
        # Test shell feature restrictions still apply
        restricted_commands = [
            "eval 'echo test'",
            "alias ll='ls -l'",
            "function test_func() { echo 'test'; }",
            "source /etc/profile",
            "`echo test`",
            "$(echo test)",
            "PATH=$PATH:/custom/path",
        ]
        
        for cmd in restricted_commands:
            stdout, stderr = executor.execute(cmd)
            assert "Security violation" in stderr, f"TIER_4 should block shell feature: {cmd}"
        
        executor.close()
        
        # Cleanup test directory
        if os.path.exists(f"{project_root}/test_dir"):
            os.rmdir(f"{project_root}/test_dir")

        # Test Tier 5: Unrestricted
        executor = BashExecutor(ShellAccessTier.TIER_5_UNRESTRICTED)
        
        # Test write operations anywhere
        stdout, stderr = executor.execute(f"touch {test_file}")
        assert stderr == "", "TIER_5 should allow writes to project"
        stdout, stderr = executor.execute("touch /tmp/test_file")
        assert stderr == "", "TIER_5 should allow writes outside project"
        
        # Test navigation
        stdout, stderr = executor.execute("cd /")
        assert stderr == "", "TIER_5 should allow unrestricted navigation"
        
        # Test normally-blocked shell features
        test_commands = [
            "eval 'echo test'",  # Test eval
            "alias ll='ls -l'",  # Test alias creation
            "function test_func() { echo 'test'; }",  # Test function definition
            "source /etc/profile",  # Test source
            "`echo test`",  # Test command substitution (backticks)
            "$(echo test)",  # Test command substitution ($())
            "shopt -s expand_aliases",  # Test shell options
            "PATH=$PATH:/custom/path",  # Test PATH modification
            "<(echo test)",  # Test process substitution
        ]
        
        for cmd in test_commands:
            stdout, stderr = executor.execute(cmd)
            assert stderr == "", f"TIER_5 should allow shell feature: {cmd}"
        
        # Test access to protected files
        stdout, stderr = executor.execute(f"echo 'test' > {protected_file}")
        assert stderr == "", "TIER_5 should allow writes to protected files"
        
        executor.close()
        
        # Cleanup
        if test_file.exists():
            test_file.unlink()
        if os.path.exists("/tmp/test_file"):
            os.unlink("/tmp/test_file")

    async def run_bash_executor_tests() -> tuple[int, int]:
        """Execute all bash executor tests sequentially.

        Returns:
            Tuple of (passed_tests, failed_tests)
        """
        tests = [
            test_access_tiers,
        ]
        
        passed = 0
        failed = 0
        
        for test in tests:
            try:
                await test()
                passed += 1
                logger.info(f"Test {test.__name__} passed")
            except Exception as e:
                import traceback
                logger.error(f"Test {test.__name__} failed:")
                logger.error(traceback.format_exc())
                failed += 1
        
        return passed, failed
