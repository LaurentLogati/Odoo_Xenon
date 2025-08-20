# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import RedirectWarning, UserError, ValidationError, AccessError
from odoo.tools import float_is_zero, float_compare, safe_eval, date_utils, email_split, email_re
from odoo.tools.misc import formatLang, format_date, get_lang

from collections import defaultdict
from datetime import date, timedelta
from itertools import groupby
from itertools import zip_longest
from hashlib import sha256
from json import dumps

import json
import re

import logging
_logger = logging.getLogger(__name__)


#forbidden fields
INTEGRITY_HASH_MOVE_FIELDS = ('date', 'journal_id', 'company_id')
INTEGRITY_HASH_LINE_FIELDS = ('debit', 'credit', 'account_id', 'partner_id')


class XenonAccountMove(models.Model):
    _inherit = 'account.move' 

    #Methode de création de facture client pour identifier les factures d'acomptes et ne pas envoyer le questionnaire de satisfaction
    
    x_advance_payment_method = fields.Selection([
        ('delivered', 'Regular invoice'),
        ('percentage', 'Down payment (percentage)'),
        ('fixed', 'Down payment (fixed amount)')
        ])
