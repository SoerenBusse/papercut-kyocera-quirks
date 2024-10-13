#!/usr/bin/env python3

"""
QUIRKS REDIRECT
- Read spool file
- Extract PJL parameters
- Remove PJL header
- Write spool file
- Call lp command
"""
import logging
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PJL_LANGUAGE = b'@PJL ENTER LANGUAGE'
PJL_LANGUAGE_REGEX = re.compile(b'@PJL ENTER LANGUAGE\\s*=\\s*(.*)\r\n')

PJL_COMMENT_OPTIONS = b'@PJL COMMENT CUPS_OPTIONS'
PJL_COMMENT_OPTIONS_REGEX = re.compile(b'@PJL COMMENT CUPS_OPTIONS\\s*=\\s*\"(.*)\"')

PJL_COPY_COUNT = b'@PJL SET COPIES'
PJL_COPY_COUNT_REGEX = re.compile(b'@PJL SET COPIES\\s*=\\s*(.*)')


def find_new_line(buffer: bytes, start_index: int, max_bytes: int) -> int:
    offset = 0
    for i in range(1, max_bytes):
        index = start_index + i

        # Only search up to the end of the buffer
        if index > len(buffer) - 1:
            break

        # Check if there's a new line at index
        if chr(buffer[index]) == '\n':
            offset = i
            break

    return offset


# Set working directory to file location directory
working_directory = os.path.dirname(os.path.realpath(__file__))
os.chdir(working_directory)

# Create logging directory
log_path = Path("logs")
log_path.mkdir(exist_ok=True)

# Setup logger
log_formatter = logging.Formatter("%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s")
logger = logging.getLogger()

fileHandler = logging.FileHandler(log_path.joinpath("quirksredirect.log"))
fileHandler.setFormatter(log_formatter)
logger.addHandler(fileHandler)

consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(log_formatter)
logger.addHandler(consoleHandler)
logger.setLevel(logging.INFO)

arg_count = len(sys.argv)
if arg_count != 7:
    logger.error(f"{sys.argv[0]} [server] [queue] [job-name] [username] [spool-file] [debug]")
    exit(1)

server = sys.argv[1]
queue = sys.argv[2]
job_name = sys.argv[3]
user_name = sys.argv[4]
spool_file = Path(sys.argv[5])
debug = sys.argv[6]

# Enable debug mode
if debug.lower() == "true":
    logger.setLevel(logging.DEBUG)
    logger.debug("Enabling debug mode requested")

# Log arguments for debugging purposes
logger.debug(f"Called redirect command with arguments: {sys.argv}")

# Get directory and name of spool file
spool_directory = spool_file.parent.absolute()
spool_name = spool_file.stem

original_options = None
original_copy_count = 1

logger.debug(f"Original spool file {spool_name} in {spool_directory}")
with open(spool_file, "rb") as spool:
    # Read first 4096 bytes to check whether there's a PCL header
    chunk = spool.read(8192)

    # Start index from where to copy the spool file to the destination file
    # Default if no PJL header found is 0
    copy_start_index = 0

    # Check if the binary data contains the search pattern
    if PJL_LANGUAGE in chunk:
        logger.debug("Found PJL header. Analysing...")
        # Search for PJL options comment and extract them if found
        if PJL_COMMENT_OPTIONS in chunk:
            # Run the regex on binary data to find the original backend options
            match = re.search(PJL_COMMENT_OPTIONS_REGEX, chunk)

            # Get options and save the original options
            if match is not None:
                original_options = match.group(1).decode("utf-8")
                logger.debug(f"Got original options \"{original_options}\"")
            else:
                logger.warning(f"Cannot parse PJL COMMENT OPTIONS")

        if PJL_COPY_COUNT in chunk:
            match = re.search(PJL_COPY_COUNT_REGEX, chunk)

            if match is not None:
                original_copy_count = int(match.group(1).decode("utf-8"))
                logger.debug(f"Got original copy count {original_copy_count}")
            else:
                logger.warning(f"Cannot parse PJL COPY COUNT")

        # Search for PJL LANGUAGE
        match = re.search(PJL_LANGUAGE_REGEX, chunk)
        if match is None:
            logger.error(
                f"Cannot find end of {PJL_LANGUAGE} in spool file.")
            # Exit will close with block
            exit(1)

        # Start with character after regex language match
        copy_start_index = match.end()

    initial_data = chunk[copy_start_index:]

    destination_spool = spool_directory.joinpath(spool_name + ".quirks")
    logger.debug(f"Write original spool except header to {destination_spool}")
    with open(destination_spool, "wb") as quirks_spool:
        # Write our initial chunk
        quirks_spool.write(initial_data)

        # Copy rest of spool to quirks file
        shutil.copyfileobj(spool, quirks_spool)

    logger.debug("Successfully copied data to destination spool")
    shutil.move(destination_spool, spool_file)
    logger.debug(f"Renamed quirks file without header to {spool_file}")

logger.debug("Run lp command")
arguments = ["lp",
             "-h", server,
             "-n", str(original_copy_count),
             "-d", queue,
             "-t", job_name,
             "-U", user_name,
             "-o",
             "raw",
             spool_file.absolute().as_posix()]

if original_options is not None:
    arguments.append("-o")
    arguments.append(original_options)

logger.debug(f"Calling {arguments}")
process_result = subprocess.run(arguments, capture_output=True, text=True)

logger.info(f"stdout: {process_result.stdout}")
logger.info(f"stderr: {process_result.stderr}")

# Check the result code
if process_result.returncode != 0:
    logger.error(f"Command returns a non zero exit code: {process_result.returncode}")
    exit(1)

exit(0)
