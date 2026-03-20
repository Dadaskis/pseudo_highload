import os
import subprocess
from pathlib import Path
from collections import defaultdict
import sys
from datetime import datetime

def get_git_logs(repo_path):
    """
    Get git logs for the repository.
    
    Args:
        repo_path: Path to the git repository
    
    Returns:
        String containing git log information
    """
    try:
        # Check if it's a git repository
        git_dir = Path(repo_path) / '.git'
        if not git_dir.exists():
            return "⚠️  Not a git repository or .git folder not found"
        
        # Get detailed git log
        cmd = [
            'git', 'log',
            '--pretty=format:%h - %ad - %an - %s',
            '--date=format:%Y-%m-%d %H:%M:%S'
        ]
        
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        
        if result.returncode == 0 and result.stdout:
            logs = result.stdout
        else:
            logs = "No git logs found or error accessing git"
        
        # Get branch information
        branch_cmd = ['git', 'branch', '--show-current']
        branch_result = subprocess.run(
            branch_cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        
        branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"
        
        # Get last commit info
        last_cmd = ['git', 'log', '-1', '--pretty=format:%h - %ad - %an - %s', '--date=format:%Y-%m-%d %H:%M:%S']
        last_result = subprocess.run(
            last_cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        
        last_commit = last_result.stdout if last_result.returncode == 0 else "No commits"
        
        # Get commit count
        count_cmd = ['git', 'rev-list', '--count', 'HEAD']
        count_result = subprocess.run(
            count_cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        
        commit_count = count_result.stdout.strip() if count_result.returncode == 0 else "0"
        
        return {
            'logs': logs,
            'branch': branch,
            'last_commit': last_commit,
            'commit_count': commit_count,
            'is_git_repo': True
        }
        
    except FileNotFoundError:
        return {
            'logs': "⚠️  Git is not installed or not accessible",
            'is_git_repo': False,
            'error': 'git_not_found'
        }
    except Exception as e:
        return {
            'logs': f"⚠️  Error accessing git: {e}",
            'is_git_repo': False,
            'error': str(e)
        }

def print_file_contents_and_stats(root_dir='.'):
    """
    Recursively print all file contents (except .pyc files) and generate statistics.
    
    Args:
        root_dir: Root directory to start scanning from
    """
    # Statistics tracking
    file_stats = defaultdict(lambda: {'count': 0, 'lines': 0, 'files': []})
    total_files = 0
    total_lines = 0
    
    # Convert to absolute path for better handling
    root_path = Path(root_dir).resolve()
    
    print("=" * 80)
    print(f"SCANNING DIRECTORY: {root_path}")
    print("=" * 80)
    print()
    
    # Walk through all directories
    for root, dirs, files in os.walk(root_path):
        # Skip __pycache__ directories
        if '__pycache__' in dirs:
            dirs.remove('__pycache__')
        
        # Skip .git directory
        if '.git' in dirs:
            dirs.remove('.git')
        
        for file in files:
            file_path = Path(root) / file
            
            # Skip .pyc files
            if file.endswith('.pyc'):
                continue
            
            # Get file extension
            extension = file_path.suffix.lower()
            if not extension:  # Files without extension
                extension = '(no extension)'
            
            try:
                # Read file contents
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.count('\n') + (1 if content and not content.endswith('\n') else 0)
                    
                    # Update statistics
                    file_stats[extension]['count'] += 1
                    file_stats[extension]['lines'] += lines
                    file_stats[extension]['files'].append(str(file_path.relative_to(root_path)))
                    total_files += 1
                    total_lines += lines
                    
                    # Print file header
                    print("-" * 60)
                    print(f"FILE: {file_path.relative_to(root_path)}")
                    print(f"TYPE: {extension if extension != '(no extension)' else 'No extension'}")
                    print(f"LINES: {lines}")
                    print("-" * 60)
                    print()
                    
                    # Print file contents
                    print(content)
                    print()
                    
            except UnicodeDecodeError:
                # Skip binary files
                print(f"⚠️  Skipping binary file: {file_path.relative_to(root_path)}")
                file_stats['(binary)']['count'] += 1
                file_stats['(binary)']['files'].append(str(file_path.relative_to(root_path)))
                continue
            except Exception as e:
                print(f"❌ Error reading {file_path.relative_to(root_path)}: {e}")
                continue
    
    # Print statistics
    print("\n" + "=" * 80)
    print("STATISTICS")
    print("=" * 80)
    print(f"\nTotal files processed: {total_files}")
    print(f"Total lines of code: {total_lines}")
    print("\nBreakdown by file type:")
    print("-" * 40)
    
    # Sort by total lines (descending)
    sorted_stats = sorted(file_stats.items(), key=lambda x: x[1]['lines'], reverse=True)
    
    for extension, stats in sorted_stats:
        if stats['count'] > 0:
            percentage = (stats['lines'] / total_lines * 100) if total_lines > 0 else 0
            print(f"\n{extension.upper()}:")
            print(f"  Files: {stats['count']}")
            print(f"  Lines: {stats['lines']} ({percentage:.1f}%)")
            if stats['files']:
                print(f"  Files list:")
                for file in sorted(stats['files']):
                    print(f"    - {file}")
    
    # Print Git logs
    print("\n" + "=" * 80)
    print("GIT LOGS")
    print("=" * 80)
    
    git_info = get_git_logs(root_path)
    
    if git_info.get('is_git_repo', False):
        print(f"\n📂 Repository: {root_path}")
        print(f"🌿 Current Branch: {git_info['branch']}")
        print(f"📊 Total Commits: {git_info['commit_count']}")
        print(f"🕐 Last Commit: {git_info['last_commit']}")
        print("\n📜 Commit History:")
        print("-" * 60)
        print(git_info['logs'])
    else:
        print(f"\n{git_info['logs']}")
        
        # Try to find git logs in parent directories
        if 'error' not in git_info or git_info.get('error') != 'git_not_found':
            print("\n🔍 Searching for git repository in parent directories...")
            parent = root_path.parent
            found_git = False
            
            while parent != parent.parent:  # Stop at filesystem root
                git_info = get_git_logs(parent)
                if git_info.get('is_git_repo', False):
                    print(f"\n✅ Found git repository at: {parent}")
                    print(f"🌿 Current Branch: {git_info['branch']}")
                    print(f"📊 Total Commits: {git_info['commit_count']}")
                    print(f"🕐 Last Commit: {git_info['last_commit']}")
                    print("\n📜 Commit History:")
                    print("-" * 60)
                    print(git_info['logs'])
                    found_git = True
                    break
                parent = parent.parent
            
            if not found_git:
                print("❌ No git repository found in current or parent directories")

if __name__ == "__main__":
    # You can specify a different root directory as a command-line argument
    root_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    
    # Check if the directory exists
    if not os.path.exists(root_dir):
        print(f"❌ Error: Directory '{root_dir}' does not exist")
        sys.exit(1)
    
    print_file_contents_and_stats(root_dir)