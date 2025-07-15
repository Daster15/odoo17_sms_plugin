{
    'name': 'SMS Platform',
    'version': '1.4',
    'author': 'Your Company',
    'category': 'Marketing',
    'summary': 'SMS via API with templates, char count, polling status',
    'depends': ['base', 'crm', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'views/sms_views.xml',           # definiuje menu_sms_root
        'views/sms_template_views.xml',  # teraz może odwołać się do menu_sms_root
        'views/sms_campaign_views.xml',
        'views/sms_conversation_views.xml',
        'views/sms_report_views.xml',
        'reports/sms_report_templates.xml',
        'reports/sms_report_actions.xml',
        'views/sms_campaign_portal_templates.xml',
        'data/cron_jobs.xml',
    ],
    'demo': [
      #  'data/sms_conversation_demo.xml',
      #  'data/sms_campanings.xml',
       # 'data/sms_demo_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'odoo17_sms_plugin/static/src/scss/sms_conversation.scss',
        ],
        'web.assets_qweb': [
          #  'odoo17_sms_plugin/static/src/xml/conversation_preview.xml',
        ],
    },
    'installable': True,
    'application': True,
}
