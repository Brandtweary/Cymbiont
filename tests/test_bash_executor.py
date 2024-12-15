if __name__ == "__main__":
    import os
    import sys
    import shutil
    from pathlib import Path
    
    # Get path to cymbiont.py
    project_root = Path(__file__).parent.parent
    cymbiont_path = project_root / 'cymbiont.py'
    
    # Re-run through cymbiont
    os.execv(sys.executable, [sys.executable, str(cymbiont_path), '--test', 'bash_executor'])
else:
    import os
    import sys
    import shutil
    from pathlib import Path
    from typing import List
    from agents.agent_types import ShellAccessTier
    from agents.bash_executor import BashExecutor
    from utils import get_paths
    from shared_resources import DATA_DIR, logger

    async def test_access_tiers():
        """Test shell access tier restrictions."""
        project_root = Path(__file__).parent.parent
        paths = get_paths(DATA_DIR)
        test_dir = project_root / "tests" / "bash_executor_test_files"
        test_file = test_dir / "test_file.txt"
        
        # Create test directory
        test_dir.mkdir(exist_ok=True)
        
        # Create test file
        test_file.write_text("test content")
        
        try:
            # Test Tier 1: Project Read-Only
            executor = BashExecutor(ShellAccessTier.TIER_1_PROJECT_READ)
            
            # Test write operations are blocked
            write_commands = [
                f"touch {test_file}",  # Create file
                f"mkdir -p {project_root}/test_dir",  # Create directory
                f"rm -f {test_file}",  # Delete file
                f"cp {test_file} {test_file}.bak",  # Copy file
                f"mv {test_file} {test_file}.bak",  # Move/rename file
            ]
            for cmd in write_commands:
                stdout, stderr = executor.execute(cmd)
                assert "Security violation" in stderr, f"TIER_1 should block write operation: {cmd}"
            
            # Reset counter after write tests
            executor.reset_kill_switch_counter()
            
            # Test read operations within project
            stdout, stderr = executor.execute(f"cat {test_file}")
            assert stderr == "", "TIER_1 should allow reading files"
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
                
            # Reset counter after read tests
            executor.reset_kill_switch_counter()
            
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
                
            # Reset counter after navigation tests
            executor.reset_kill_switch_counter()
                
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
                f"rm -f {test_file}",  # Delete file
                f"cp /etc/hosts {test_file}",  # Copy file
                f"mv {test_file} {test_file}.bak",  # Move/rename file
            ]
            for cmd in write_commands:
                stdout, stderr = executor.execute(cmd)
                assert "Security violation" in stderr, f"TIER_2 should block write operation: {cmd}"
                
            # Reset counter after write tests
            executor.reset_kill_switch_counter()
            
            # Test read operations within project
            stdout, stderr = executor.execute(f"cat {test_file}")
            assert stderr == "", "TIER_2 should allow reading files"
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
            executor = BashExecutor(ShellAccessTier.TIER_3_PROJECT_RESTRICTED_WRITE)
            
            # Test writes in agent workspace (should be allowed)
            stdout, stderr = executor.execute(f"touch {paths.agent_workspace_dir}/test_file.txt")
            assert stderr == "", "TIER_3 should allow writes in agent_workspace"
            stdout, stderr = executor.execute(f"mkdir -p {paths.agent_workspace_dir}/test_dir")
            assert stderr == "", "TIER_3 should allow directory creation in agent_workspace"
            
            # Test writes outside agent workspace (should be blocked)
            stdout, stderr = executor.execute(f"touch {test_file}")
            assert "Security violation" in stderr, "TIER_3 should block writes outside agent_workspace"
            stdout, stderr = executor.execute(f"mkdir -p {project_root}/test_dir")
            assert "Security violation" in stderr, "TIER_3 should block directory creation outside agent_workspace"
            
            # Test navigation - should be allowed anywhere (read-only)
            stdout, stderr = executor.execute("cd /")
            assert stderr == "", "TIER_3 should allow system-wide navigation"
            stdout, stderr = executor.execute("cd /tmp")
            assert stderr == "", "TIER_3 should allow navigation to system directories"
            stdout, stderr = executor.execute(f"cd {project_root}")
            assert stderr == "", "TIER_3 should allow navigation back to project"
            
            # Cleanup agent workspace test files
            executor.execute(f"rm -rf {paths.agent_workspace_dir}/test_file.txt")
            executor.execute(f"rm -rf {paths.agent_workspace_dir}/test_dir")
            
            executor.close()

            # Test Tier 4: Full Project Write
            executor = BashExecutor(ShellAccessTier.TIER_4_PROJECT_WRITE_EXECUTE)
            
            # Test write operations within project, including protected files
            stdout, stderr = executor.execute(f"touch {test_file}")
            assert stderr == "", "TIER_4 should allow project writes"
            stdout, stderr = executor.execute(f"mkdir -p {project_root}/test_dir")
            assert stderr == "", "TIER_4 should allow directory creation"
            stdout, stderr = executor.execute(f"echo 'test' > {test_file}")
            assert stderr == "", "TIER_4 should allow file modification"
            
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
            
            executor.close()
            
        finally:
            # Cleanup
            if os.path.exists(test_file):
                os.remove(test_file)
            if os.path.exists(test_dir):
                shutil.rmtree(test_dir)
            # Clean up test_dir in project root if it exists
            project_test_dir = project_root / "test_dir"
            if os.path.exists(project_test_dir):
                shutil.rmtree(project_test_dir)

    async def test_kill_switches():
        """Test kill switch behavior for blocked commands."""
        project_root = Path(__file__).parent.parent
        
        # Create new executor for kill switch test
        executor = BashExecutor(ShellAccessTier.TIER_1_PROJECT_READ)
        
        # Commands that will be blocked
        blocked_commands = [
            "touch /etc/test",  # Outside project
            "rm -rf /",         # Outside project
            "cd /etc",          # Outside project navigation
            "cat /etc/passwd",  # Outside project read
            "mkdir /var/test",  # Outside project
            "cp /etc/hosts /tmp",  # Outside project
            "mv /etc/hosts /tmp",  # Outside project
            "chmod 777 /etc/hosts",  # Outside project
            "ln -s /etc/hosts /tmp/hosts"  # Outside project symlink
        ]
        
        try:
            # Test first 3 commands - counter should increment but no warnings
            for i, cmd in enumerate(blocked_commands[:3], 1):
                stdout, stderr = executor.execute(cmd)
                assert stdout == "", f"Command {i} should have empty stdout"
                assert "Security violation" in stderr, f"Command {i} should be blocked"
                assert executor.blocked_commands == i, f"Blocked commands counter should be {i}"
            
            # Test warning at 4th blocked command
            stdout, stderr = executor.execute(blocked_commands[3])
            assert stdout == ""
            assert "Security violation" in stderr
            assert executor.blocked_commands == 4
            
            # Test commands 5-8, counter should increment with warnings
            for i, cmd in enumerate(blocked_commands[4:8], 5):
                stdout, stderr = executor.execute(cmd)
                assert stdout == "", f"Command {i} should have empty stdout"
                assert "Security violation" in stderr, f"Command {i} should be blocked"
                assert executor.blocked_commands == i, f"Blocked commands counter should be {i}"
            
            # Test 9th command - should trigger critical warning
            stdout, stderr = executor.execute(blocked_commands[8])
            assert stdout == ""
            assert "Security violation" in stderr
            assert executor.blocked_commands == 9, "Blocked commands counter should be 9"
            
            # Note: We don't test the 10th command as it would terminate the program
            
        finally:
            executor.close()

    async def run_bash_executor_tests() -> tuple[int, int]:
        """Execute all bash executor tests sequentially.

        Returns:
            Tuple of (passed_tests, failed_tests)
        """
        tests = [
            test_kill_switches,  # Run kill switch test first since it relies on blocked command count
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
