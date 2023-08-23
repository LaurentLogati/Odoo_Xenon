# -*- coding: utf-8 -*-
from . import Xenon_sale
from . import Xenon_sale_purchase_sale_order
from . import Xenon_purchase
from . import Xenon_calcul_prix
from . import Xenon_sale_stock_sale_order
from . import Xenon_purchase_stock_rule
from . import Xenon_purchase_purchase_stock
from . import Xenon_portal
from . import Xenon_account_move
from . import Xenon_sale_advance_payment_inv
from . import Xenon_account_payment
from . import Xenon_product
from . import Xenon_stock

from odoo.api import Environment, SUPERUSER_ID


def _synchronize_cron(cr, registry):
    env = Environment(cr, SUPERUSER_ID, {'active_test': False})
    send_invoice_cron = env.ref('sale.send_invoice_cron', raise_if_not_found=False)
    if send_invoice_cron:
        config = env['ir.config_parameter'].get_param('sale.automatic_invoice', False)
        send_invoice_cron.active = bool(config)