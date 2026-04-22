# log.py
import os
import inspect
import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler

def setup_logger(name="app", log_filename=None, log_level=logging.INFO, console_output=True):    
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    
    if log_filename is None:
        if name == '__main__':
            actual_filename = 'main.log'
        else:
            actual_filename = f"{name.replace('.', '_')}.log"
    else:
        actual_filename = log_filename
    
    log_path = os.path.join(log_dir, actual_filename)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    
    if logger.handlers:
        logger.handlers.clear()
    
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    if console_output:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    return logger

def get_logger(log_filename=None):    
    caller_frame = inspect.currentframe().f_back
    if caller_frame:
        module_name = caller_frame.f_globals.get('__name__', 'app')
    else:
        module_name = 'app'
    
    return setup_logger(module_name, log_filename)