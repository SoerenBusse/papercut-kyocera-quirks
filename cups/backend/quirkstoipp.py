#!/usr/bin/env python3
"""
CUPS BACKEND
- Remove PJL Header
- Translate file-in to stdout
"""
import logging
import os
import re
import shutil
import sys
from pathlib import Path

# !/usr/bin/env python3

"""
QUIRKS REDIRECT
- Read spool file
- Extract PJL parameters
- Remove PJL header
- Write spool file
- Call lp command
"""
PJL_COPY_COUNT = b'@PJL SET COPIES'
PJL_COPY_COUNT_REGEX = re.compile(b'@PJL SET COPIES\\s*=\\s*(.*)')

PJL_COMMENT_OPTIONS = b'@PJL COMMENT CUPS_OPTIONS'
PJL_COMMENT_OPTIONS_REGEX = re.compile(b'@PJL COMMENT CUPS_OPTIONS\\s*=\\s*\"(.*)\"')

PJL_COMMENT_PPD = b'@PJL COMMENT PPD'
PJL_COMMENT_PPD_REGEX = re.compile(b'@PJL COMMENT PPD\\s*=\\s*"(.*)\"')

PJL_LANGUAGE = b'@PJL ENTER LANGUAGE'
PJL_LANGUAGE_REGEX = re.compile(b'@PJL ENTER LANGUAGE\\s*=\\s*(.*)\r\n')


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


def parse_device_uri(device_uri: str) -> str:
    # Exmaple: quirkstoipp:ipp://192.168.1.1?waitjob=false&waitprinter=false
    # Get our backend name, which should be first parameter in the DEVICE_URI
    backend_name = Path(__file__).stem

    parts = device_uri.split(":", 1)

    # Should have two elements
    if len(parts) != 2:
        logger.error("Device URI doesn't contain two backends")
        exit(1)

    if parts[0] != backend_name:
        logger.error("Device URI doesn't start with this backend")
        exit(1)

    if not parts[1].startswith("ipp"):
        logger.error("Currently only ipp is supported as parent backend")

    # Return new device uri
    return parts[1]


# Set working directory to file location directory
working_directory = Path("/tmp/quirkstoipp")
working_directory.mkdir(exist_ok=True)
os.chdir(working_directory)

# Create logging directory
log_directory = Path("logs")
log_directory.mkdir(exist_ok=True)

# Create destination spool
destination_spool_directory = Path("spool")
destination_spool_directory.mkdir(exist_ok=True)

# Setup logger
log_formatter = logging.Formatter("%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s")
logger = logging.getLogger()

# Write to file
fileHandler = logging.FileHandler(log_directory.joinpath("quirksredirect.log"))
fileHandler.setFormatter(log_formatter)
logger.addHandler(fileHandler)

# Write to stderr, which will be forwarded to CUPS error_log
consoleHandler = logging.StreamHandler(sys.stderr)
consoleHandler.setFormatter(log_formatter)
logger.addHandler(consoleHandler)
logger.setLevel(logging.DEBUG)

# Log arguments for debugging purposes
logger.debug(f"Called backend with argv arguments: {sys.argv}")

# We expect 6 or 7 arguments
argcount = len(sys.argv)
if argcount == 1:
    print("network quirkstoipp \"Unknown\" \"PaperCut Quirks Restore\"")
    exit(0)

# We're currently only supporting supplying the spool file as 7th argument, because we're sure we're getting a PDF
# and need to always send the IPP options
# TODO: Add stdin to temporary spool file
if argcount != 7:
    logger.warning("CUPS backend currently only supports spool via file parameter and not stdin")
    exit(1)

backend_path = sys.argv[0]
job_id = sys.argv[1]
username = sys.argv[2]
job_name = sys.argv[3]
copy_count = sys.argv[4]
raw_options = sys.argv[5]
source_spool_file = Path(sys.argv[6])

if "CUPS_SERVERBIN" not in os.environ:
    logger.error("Missing mandatory environment variable CUPS_SERVERBIN")
    exit(1)

cups_server_bin = Path(os.environ["CUPS_SERVERBIN"])

if "DEVICE_URI" not in os.environ:
    logger.error("Missing mandatory environment variable: DEVICE_URI")
    exit(1)

child_device_uri = parse_device_uri(os.environ["DEVICE_URI"])

if "PPD" not in os.environ:
    logger.error("Missing mandatory environment variable: PPD")

ppd = os.environ.get("PPD")

# Get directory and name of spool file
source_spool_directory = source_spool_file.parent.absolute()
source_spool_name = source_spool_file.stem

new_options = ""
new_copy_count = 1

# By default we're setting the ppd to the PPD this backend was called with
# If we're having a different PPD in PJL replace it
new_ppd = ppd

logger.debug(f"Original spool file {source_spool_name} in {source_spool_directory}")
with open(source_spool_file, "rb") as spool:
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
                new_options = match.group(1).decode("utf-8")
                logger.debug(f"Got original options \"{new_options}\"")
            else:
                logger.warning(f"Cannot parse PJL COMMENT OPTIONS")

        if PJL_COPY_COUNT in chunk:
            match = re.search(PJL_COPY_COUNT_REGEX, chunk)

            if match is not None:
                new_copy_count = int(match.group(1).decode("utf-8"))
                logger.debug(f"Got original copy count {new_copy_count}")
            else:
                logger.warning(f"Cannot parse PJL COPY COUNT")

        if PJL_COMMENT_PPD in chunk:
            match = re.search(PJL_COMMENT_PPD_REGEX, chunk)
            if match is not None:
                new_ppd = match.group(1).decode("utf-8")
            else:
                logger.warning(f"Cannot parse PJL COMMENT PPD")

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

    destination_spool = destination_spool_directory.joinpath(f"{source_spool_name}.quirks")
    logger.debug(f"Write original spool except header to {destination_spool}")
    with open(destination_spool, "wb") as quirks_spool:
        # Write our initial chunk
        quirks_spool.write(initial_data)

        # Copy rest of spool to quirks file
        shutil.copyfileobj(spool, quirks_spool)

    logger.debug("Successfully copied data to destination spool")

logger.info(f"Restored parameters: Copy Count: {new_copy_count}, PPD: {new_ppd}, Options: {new_options}")

new_environment = os.environ.copy()
new_environment["PPD"] = new_ppd
new_environment["DEVICE_URI"] = child_device_uri

logger.debug(f"New environment variables: {new_environment}")

# TODO: Delete copied spool files.
# Call IPP Backend by replacing the current process
# l: fixed arguments
# p: path variable
# e: envionment
ipp_backend = cups_server_bin.joinpath("backend").joinpath("ipp").absolute().as_posix()
logger.debug(f"Call ipp backend at {ipp_backend} with Device-URI {child_device_uri}")
os.execlpe(ipp_backend, ipp_backend, job_id, username, job_name, str(new_copy_count), new_options,
           destination_spool.absolute().as_posix(), new_environment)
