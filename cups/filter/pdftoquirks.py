#!/usr/bin/env python3
"""
CUPS FILTER
- Add PJL values for Duplex, Color, Media Size
- Add cups options as PJL comment
"""
import logging
import shutil
import sys

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, encoding="utf-8")

# Log arguments for debugging purposes
logger.debug(f"Called filter with argv arguments: {sys.argv}")

argcount = len(sys.argv)

# We expect 6 or 7 arguments
if argcount < 6 or argcount > 7:
    logger.error("Not enough or too many arguments. Pass 6 or 7 arguments")

    exit(1)

filter_path = sys.argv[0]
job_id = sys.argv[1]
username = sys.argv[2]
filename = sys.argv[3]
copy_count = sys.argv[4]
raw_options = sys.argv[5]

# Parse relevant parameters for PaperCut
options = {}

for option in raw_options.split():
    if "=" in option:
        key, value = option.split("=")
        options[key.lower()] = value

# Duplex
duplex_enabled = False
if "duplex" in options and (
        options["duplex"].lower() == "duplextumble" or options["duplex"].lower() == "duplexnotumple"):
    duplex_enabled = True

# Check for gray value, to accept any other color code like RGB or CMYK
# Add american and british spelling just to be sure ;)
gray = False
if "colormodel" in options and options["colormodel"].lower() == "gray" or options["colormodel"].lower() == "grey":
    gray = True

# Default Media Size
page_size = "A4"
if "pagesize" in options:
    page_size = options["pagesize"]

logger.info(f"Parsed parameters from IPP: Duplex: {duplex_enabled}, Gray: {gray}, PageSize: {page_size}")

# Write PJL Header
# PJL Escape Sequence
# Prevents that the printer prints garbage, when this file is accidentially send to the printer
sys.stdout.write("\x1B%-12345X@PJL\r\n")

# Write Duplex Value. We can ignore the bindung here. PaperCut doesn't care for analysis
sys.stdout.write(f"@PJL SET DUPLEX={"ON" if duplex_enabled else "OFF"}\r\n")
sys.stdout.write(f"@PJL SET RENDERMODE={"GRAYSCALE" if gray else "COLOR"}\r\n")
sys.stdout.write(f"@PJL SET PAPER={page_size}\r\n")
sys.stdout.write(f"@PJL SET COPIES={copy_count}\r\n")

# Options als Comment einfügen
sys.stdout.write(f"@PJL COMMENT CUPS_OPTIONS=\"{raw_options}\"\r\n")

# Tell printer that PDF follows
# We're copying the inconsistency spaces from CUPS. Don't know if its important ;)
sys.stdout.write(f"@PJL ENTER LANGUAGE = PDF\r\n")

# Important to flush. Otherwise, shutils.copyfileobj will be before this one in the output file.
sys.stdout.flush()

# Do we have 7 arguments?
# Then read input from passed file
if argcount == 7:
    file_path = sys.argv[6]
    logger.debug(f"Reading spool file from {file_path} and write to stdout")

    with open(file_path, "rb") as spool_in:
        shutil.copyfileobj(spool_in, sys.stdout.buffer)
else:
    logger.debug(f"Reading spool file from stdin and write to stdout")
    shutil.copyfileobj(sys.stdin.buffer, sys.stdout.buffer)

# Exit with successful return code
exit(0)
