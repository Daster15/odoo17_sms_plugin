from odoo import http, fields
from odoo.http import request

class SmsController(http.Controller):
    @http.route('/sms/incoming', type='json', auth='public', methods=['POST'], csrf=False)
    def sms_incoming(self, **kwargs):
        partner = request.env['res.partner'].search([('phone','=',kwargs.get('from'))], limit=1)
        conv = request.env['sms.conversation'].search([('partner_id','=',partner.id)], limit=1)
        if not conv:
            conv = request.env['sms.conversation'].create({'partner_id': partner.id})
        request.env['sms.conversation.line'].create({
            'conversation_id': conv.id,
            'body': kwargs.get('text'),
            'date': fields.Datetime.now(),
            'direction': 'in'
        })
        return {'status': 'ok'}
