import sys
import re
from datetime import date
from loguru import logger
 
# Only import Qt components if not running in container
try:
    from PySide6.QtWidgets import QTextEdit
    from PySide6.QtGui import QColor
    from PySide6.QtCore import QObject, Signal, Slot
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False

# Rest of the code wrapped in appropriate checks
if QT_AVAILABLE:
    class LogSignals(QObject):
        new_log = Signal(str, dict)
    
    class QTextEditHandler:
        def __init__(self, text_edit: QTextEdit):
            self.text_edit = text_edit
            self.signals = LogSignals()
            self.signals.new_log.connect(self.append_message)

        def write(self, message: str):
            clean_message = clean_brackets(message)
            
            # Define colors based on logging level
            if "ERROR" in message:
                colors = {
                    "time": QColor("#00FF00"),  # green
                    "level": QColor("#FF0000"),  # red
                    "message": QColor("#FF0000")  # red
                }
            elif "WARNING" in message:
                colors = {
                    "time": QColor("#27e868"),  # green
                    "level": QColor("#FFD700"),  # yellow
                    "message": QColor("#FFD700")  # yellow
                }
            elif "INFO" in message:
                colors = {
                    "time": QColor("#27e868"),  # green
                    "level": QColor("#32c2c2"),  # blue
                    "message": QColor("#FFFFFF")  # white
                }
            else:
                colors = {
                    "time": QColor("#27e868"),  # green
                    "level": QColor("#d137d4"),  # blue
                    "message": QColor("#eb811e")  # orange
                }
            
            # Send signal to update UI
            self.signals.new_log.emit(clean_message, colors)

        @Slot(str, dict)
        def append_message(self, message: str, colors: dict):
            # Split message into parts
            parts = message.split(" ", 2)
            if len(parts) >= 3:
                time_part, level_part, message_part = parts

                # Add timestamp
                self.text_edit.setTextColor(colors["time"])
                self.text_edit.insertPlainText(time_part + " ")

                # Add log level
                self.text_edit.setTextColor(colors["level"])
                self.text_edit.insertPlainText(level_part + " ")

                # Add message content
                self.text_edit.setTextColor(colors["message"])
                self.text_edit.insertPlainText(message_part + "\n")

            # Scroll to bottom
            scrollbar = self.text_edit.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())


    def logging_setup(gui_mode=False, text_edit=None):
        """
        Sets up logging configuration for both GUI and console modes.
        
        Args:
            gui_mode (bool): If True, logs will be directed to QTextEdit widget
            text_edit (QTextEdit): Text widget for displaying logs in GUI mode
        """
        format_info = "<green>{time:HH:mm:ss.SS}</green> <blue>{level}</blue> <level>{message}</level>"
        format_error = "<green>{time:HH:mm:ss.SS}</green> <blue>{level}</blue> | " \
                       "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | <level>{message}</level>"
        file_path = r"logs/"

        logger.remove()  # Remove all previous handlers

        if gui_mode and text_edit is not None:
            # In GUI mode, add only QTextEdit handler
            handler = QTextEditHandler(text_edit)
            logger.add(handler, format=format_info, level="INFO")
        else:
            # In console mode, add handlers for both file and stdout
            logger.add(file_path + f"out_{date.today().strftime('%m-%d')}.log", colorize=True,
                       format=format_info)
            logger.add(sys.stdout, colorize=True, format=format_info, level="INFO")


    def clean_brackets(raw_str):
        """
        Removes HTML-style brackets from string.
        
        Args:
            raw_str (str): Input string containing HTML-style brackets
            
        Returns:
            str: Cleaned string without brackets
        """
        clean_text = re.sub(brackets_regex, '', raw_str)
        return clean_text


    # Regex pattern for matching HTML-style brackets
    brackets_regex = re.compile(r'<.*?>')

    # Example usage (assuming `text_edit` is your QTextEdit instance):
    logging_setup(gui_mode=False)
else:
    # Dummy classes for non-GUI environment
    class LogSignals:
        pass
    
    class QTextEditHandler:
        def __init__(self, *args, **kwargs):
            pass
        def write(self, message):
            print(message)
