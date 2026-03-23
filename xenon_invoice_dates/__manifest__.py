{
    'name': 'Xenon Invoice Start End Dates Display',
    'version': '18.0.1.0.0',
    'summary': 'Affichage des dates début/fin sur les lignes de facture',
    'author': 'Xenon',
    'depends': ['account', 'account_invoice_start_end_dates'],
    'data': [
        'views/account_move_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'xenon_invoice_dates/static/src/invoice_line_dates.js',
        ],
    },
    'installable': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
