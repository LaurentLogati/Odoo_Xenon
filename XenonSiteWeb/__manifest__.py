{
    'name': 'Xenon Site Web',
    'version': '1.0',
	'author':"Laurent LOEZIC",
    'category': 'Site',
    'summary': 'Site web Xenon',
	'depends':['web', 'website', 'theme_treehouse', 'theme_common'],
    'data': ['views/theme_xenon.xml', 'views/xenon_layout.xml'],
    'css' : ['static/src/css/theme_xenon.scss'],
	'demo':[],
    'installable': True,
    'assets': {
        'web.assets_backend': [
            'XenonSiteWeb/static/src/css/theme_xenon.scss',
        ],
        'web.assets_frontend': [
            'XenonSiteWeb/static/src/css/theme_xenon.scss',
        ],
    },
}