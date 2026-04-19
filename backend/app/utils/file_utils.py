from typing import Tuple, Optional


def format_file_size(bytes_size: int, target_unit: Optional[str] = None) -> Tuple[float, Optional[str]]:
    """Convert bytes to human-readable file size format."""
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    
    if target_unit:
        try:
            index = units.index(target_unit)
        except ValueError:
            index = 0
        for _ in range(index):
            bytes_size /= 1024
        return round(bytes_size, 2), None
    else:
        index = 0
        while bytes_size >= 1024 and index < len(units) - 1:
            bytes_size /= 1024
            index += 1
        return round(bytes_size, 2), units[index]
