PR Infra's bills carry a receipt-register ("DMR") stamp with a number and a date,
a "received" signature, and often a handwritten site note naming the plant or
site the goods or work went to.

- Record the DMR stamp in `document.receipt_register`. File names start with the
  DMR number; a file name is never evidence of the invoice number.
- A site note is evidence of where the cost belongs. When the company keeps cost
  centres for its sites and the note names one (`cost_centres`), allocate the bill
  to it and quote the note. An unclear site note holds the bill with
  `classification_uncertain`, quoting what can be read.
