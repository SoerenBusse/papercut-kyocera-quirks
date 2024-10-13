# PaperCut Kyocera Quirks
This is a an unofficial repository to support IPP printing on Kyocera TASKalfa devices using PaperCut MF on Linux.
Background is a broken and very slow postscript stack of the Kyocera printers, which makes printing of some complex PDF files very slow.

Documentation of the bugs and challenges is in progress.

## Challenges
### Big Postscript files with slow Kyocera Postscript interpreter
TODO

### Kyocera handling coexistence of parameters in Postscript/PJL and IPP
When only setting `duplex=on` inside postscript / pjl without sending the option `sides=two-sided-long-edge` via IPP the printer prints, as expected, the page duplex.

When setting `duplex=on` inside postscript/pjl with sending the option `sides=two-sided-long-edge` via IPP the printer prints the page only single sided.
This is somehow ... strange. So whenever you have a conflict of parameters inside of Postscript/PJL and IPP the behaviour is unexpected.

This contradicts https://datatracker.ietf.org/doc/html/rfc8011#appendix-C.2. It should prefer either Postscript/PJL OR IPP, but it does neither of it.

Therefore, we have to make sure that whenever we send a Postscript file via IPP on Kyocera to never send the associated IPP options.
Normally this is handled by CUPS internally by only sending IPP options when the spool file is a PDF file.

### PaperCut spool analysis
By default, PaperCut analysis the spool file for attributes like Duplex, Color.
PaperCut supports, as far as I see, only PDF with PJL or Postscript for print analysis.

These analysis result is used for accounting as well as showing the job information on the release station.

When printing to an IPP Everywhere printer the spool file is only the PDF file, without any PJL header or Postscript metadata.
Therefore, by default PaperCut will not account printing to ipp-everywhere correctly and will not show duplex / color at the release-station.

It would be useful to have PaperCut analyse the CUPS option, when no Postscript / PJL information is found
to support IPP Everywhere printers, which works absolutely hassle-free on simple desk printers and MFPs.

### PaperCut Backend Call Behaviour 
#### stdin / as file
There's an implicit, undocumented behaviour of CUPS when the IPP job-options are send:

The IPP job-options are only send when ...
- ... the spool file is send via stdin to the ipp-backend AND the final-content-type is "application/pdf", "application/vnd.cups-pdf" or "image/*"
- ... **OR** the spool file is passed as 6th argument

https://github.com/OpenPrinting/cups/blob/master/backend/ipp.c#L591

By default, CUPS will always send postscript spool files via stdin to the ipp backend. 
Because it's not a PDF/Image the IPP job-options are never send and the issue described in [Kyocera handling coexistence](#Kyocera handling coexistence of parameters in Postscript/PJL and IPP) will not happen.

However, PaperCut is using `lp -o raw` as redirect command after releasing the print job.
In this specific case, because there's no filter, CUPS will forward the spool as 6th parameter to the IPP-backend.
Therefore, the IPP backend is adding the job-options and is will trigger the bug as described in [Kyocera handling coexistence](#Kyocera handling coexistence of parameters in Postscript/PJL and IPP)

PaperCut must preserve the call behaviour after releasing the job.

Using the LPD backend won't have this issue. 
However, IPP is mandatory to send print-job encrypted to the printer.

#### IPP-options after job release
There's an issue that PaperCut is not forwarding the cups options it's received after releasing the print-job.

Normally PaperCut should save the cups options received when the papercut-backend is called and the job is hold.
After release PaperCut should call the redirect command with these saved cups options via the `lp -o raw -o %saved_options%`.

This is mandatory to allow ipp-everywhere print-jobs (Direct PDF Print), which is mandatory to support fast printing on printers with a broken postscript stack as Kyocera TASKalfa.


### COPY-Count?

## Quirks
### CUPS-FILTER: pdftoquirks
The aim of this filter is to append PJL attributes before the PDF file.
The PaperCut Backend analysis this PJL attributes and determines whether the side is Duplex, Grayscale 
and shows the correct values on the release station / device. 

_Sadly PaperCut doesn't seem to support analysing the IPP options directly and is only analysing the spool-file._

Additionally, we'll save the cups options (like sides=, media=) as PJL comment inside the spool-file to later restore it inside the backend before calling the ipp backend.

The PJL attributes must be removed again after the PaperCut Backend because of another Kyocera Bug.

#### Why not using the "Generic PDF Printer"
Mobility Print analysis the PPD file of the printer, which expects the content as
```
*PageSize A4/A4: "<</PageSize[595.28 841.89]/ImagingBBox null>>setpagedevice"
```

However, the Generic PDF Printer specifies PJL commands for the page size, which Mobility Print don't understand.
```
Failed to parse the paperSize, error invalid CUPS page size format: *PageSize A4/A4: "@PJL SET PAPER=A4<0A>"
```

Additionally, there's no public documentation how to do Staple/Punching using PJL commands on Kyocera printers.  

### REDIRECT: quirksredirect
The aim of this command is to be used as `redirect_cmd` in `print-provider.conf`.
This wraps the original `lp` call, but before reads the PJL header from the spool and restores the original copy-count and options and pass it to the `lp` command.

Additionally, it removes the PJL header, because of [Kyocera handling coexistence](#Kyocera handling coexistence of parameters in Postscript/PJL and IPP)

```
./quirksredirect [server] [queue] [job-name] [spool-file] [debug
```