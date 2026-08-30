import subprocess
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

def run_sync_cmd(cmd: List[str], timeout: int = 600) -> Tuple[int, str, str]:
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        return (
            proc.returncode,
            stdout.decode('utf-8', errors='ignore'),
            stderr.decode('utf-8', errors='ignore')
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        return (-1, '', f'Command timed out after {timeout} seconds')
    except Exception as e:
        return (-1, '', str(e))
