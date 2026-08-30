import os
import zipfile
import logging
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

class Packager:
    @staticmethod
    def create_zip(files: List[Path], output_zip_path: Path) -> Path:
        output_zip_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output_zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zipf:
            for file_path in files:
                if file_path.exists():
                    zipf.write(file_path, arcname=file_path.name)
        return output_zip_path

packager = Packager()
