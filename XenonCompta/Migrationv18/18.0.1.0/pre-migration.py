import logging

_logger = logging.getLogger(__name__)

    
def migrate(cr, version):
    _logger.info('Start script for deactivating module')
    _logger.info(f'Version: {version}')
    cr.execute("DELETE FROM ir_module_module WHERE name ILIKE 'XenonCompta'")
    cr.execute("DELETE FROM ir_module_module WHERE name ILIKE 'account_cutoff_base'")
    cr.execute("DELETE FROM ir_module_module WHERE name ILIKE 'account_cutoff_start_end_dates'")
    cr.execute("DELETE FROM ir_module_module WHERE name ILIKE 'account_financial_report'")
    cr.execute("DELETE FROM ir_module_module WHERE name ILIKE 'account_invoice_margin'")
    cr.execute("DELETE FROM ir_module_module WHERE name ILIKE 'account_invoice_margin_sale'")
    cr.execute("DELETE FROM ir_module_module WHERE name ILIKE 'account_invoice_start_end_dates'")
    cr.execute("DELETE FROM ir_module_module WHERE name ILIKE 'date_range'")
    cr.execute("DELETE FROM ir_module_module WHERE name ILIKE 'report_xlsx'")
    _logger.info('Stop script for deactivating module')
