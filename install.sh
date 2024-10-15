#!/bin/bash
echo "Copy Filter"
cp cups/filter/pdftoquirks.py /usr/lib/cups/filter/pdftoquirks
chmod +x /usr/lib/cups/filter/pdftoquirks

echo "Copy Backend"
cp cups/backend/quirkstoipp.py /usr/lib/cups/quirkstoipp
chmod +x /usr/lib/cups/quirkstoipp

systemctl restart cups