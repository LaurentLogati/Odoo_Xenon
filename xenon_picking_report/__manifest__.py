{
    'name': 'Xenon Picking Report',
    'version': '18.0.1.0.0',
    'summary': 'Ajout code analytique et x_emplacement sur rapport picking',
    'author': 'Xenon',
    'depends': ['stock', 'sale_stock'],
    'data': [
        'views/report_picking_custom.xml',
    ],
    'installable': True,
    'auto_install': False,
}
