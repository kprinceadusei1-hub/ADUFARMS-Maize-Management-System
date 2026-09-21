document.addEventListener('DOMContentLoaded', function () {
  const printButton = document.getElementById('printInvoiceButton');
  const invoicePage = document.querySelector('.invoice-page');

  function printInvoice() {
    window.print();
  }

  if (printButton) {
    printButton.addEventListener('click', printInvoice);
  }

  if (invoicePage && invoicePage.dataset.autoprint === '1') {
    window.setTimeout(printInvoice, 350);
  }
});
