from odoo import models, fields, api
import logging
import requests
import re
from odoo.tools.safe_eval import safe_eval

_logger = logging.getLogger(__name__)

class SmsMessage(models.Model):
    _name = 'sms.message'
    _description = 'SMS Message'

    template_id = fields.Many2one('sms.template', string='Template', help='Select SMS template')
    body = fields.Text(string='Message', required=True)
    char_count = fields.Integer(string='Chars', compute='_compute_char_count', store=True)
    partner_id = fields.Many2one('res.partner', string='Customer', index=True)
    group_ids = fields.Many2many('res.partner', string='Customer Groups')
    campaign_id = fields.Many2one('sms.campaign', string='Campaign', index=True)
    date_scheduled = fields.Datetime(string='Scheduled Date', index=True)
    state = fields.Selection([
        ('draft', 'Oczekujące'),
        ('scheduled', 'Zaplanowane'),
        ('sent', 'Wysłane'),
        ('delivered', 'Dostarczone'),
        ('failed', 'Nieudane')
    ], default='draft', index=True)
    message_type = fields.Selection(
        [('sms', 'SMS'), ('notification', 'Notification')],
        string='Message Type',
        default='sms'
    )

    external_id = fields.Char(string='External SMS ID', help='ID from SMS provider')

    sender_number = fields.Selection(
        selection='_get_available_sender_numbers',
        string='Sender Number',
        required=True,
        default=lambda self: self._get_default_sender_number()
    )

    sms_gateway_response = fields.Text(string='SMS Gateway Response')



    def _get_available_sender_numbers(self):
        """Zwraca listę dostępnych numerów nadawcy"""
        return [
            ('+48123456789', 'CLIP (POXBOX)'),
            ('+48987654321', 'Marketing (+48 600 100 100)'),
            ('+48111222333', 'Support (+48 600 200 200)')
        ]

    def _get_default_sender_number(self):
        """Zwraca domyślny numer nadawcy"""
        numbers = self._get_available_sender_numbers()
        return numbers[0][0] if numbers else False

    # Hardcoded API credentials and URL
    API_USERNAME = 'zadmin'
    API_PASSWORD = 'P@ssPOXskademo'
    API_URL = 'https://skademo.poxbox.pl/'

    @api.onchange('template_id', 'partner_id', 'campaign_id')
    def _onchange_template(self):
        """Po wybraniu szablonu podstaw body i wyrenderuj {{ … }}."""
        for rec in self:
            if not rec.template_id:
                rec.body = False
                continue
            raw_body = rec.template_id.body or ''
            # wzorzec: wszystko między podwójnymi klamrami
            pattern = re.compile(r'{{\s*(.*?)\s*}}')

            def _replace(match):
                expr = match.group(1)
                try:
                    # safe_eval wykona np. object.partner_id.name
                    value = safe_eval(expr, {'object': rec})
                    return str(value or '')
                except Exception:
                    # w razie błędu zostaw oryginalny placeholder
                    return match.group(0)

            rec.body = pattern.sub(_replace, raw_body)
            # odśwież licznik znaków, jeśli potrzebujesz
            rec._compute_char_count()

    @api.depends('body')
    def _compute_char_count(self):
        for rec in self:
            rec.char_count = len(rec.body or '')

    @api.onchange('template_id')
    def _onchange_template(self):
        if self.template_id:
            self.body = self.template_id.body

    @api.model
    def _call_api(self, method, payload):
        endpoint = f"{self.API_URL.rstrip('/')}/smsapi/{method}"
        try:
            resp = requests.post(endpoint, json=payload, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            _logger.error('%s error: %s', method, e)
            return False

    @api.model
    def send_sms_to_number_old(self, phone_number, message_text, sender_number=None, scheduled_date=None):
        """
        Send a single SMS to the given phone number.
        :param phone_number: numer telefonu (string), np. '+48123456789'
        :param message_text: treść wiadomości
        :param sender_number: (opcjonalnie) numer nadawcy,
                              jeśli nie podano, użyty zostanie domyślny
        :param scheduled_date: (opcjonalnie) datetime, jeśli chcesz zaplanować wysyłkę
        :return: odpowiedź z API (dict) lub False przy błędzie
        """
        if not phone_number:
            _logger.error("Brak numeru telefonu do wysłania SMS")
            return False

        # wybór numeru nadawcy
        sender = sender_number or self._get_default_sender_number()

        # przygotowanie wiadomości
        msg = {
            'destination_number': phone_number,
            'text': message_text,
        }
        payload = {
            'username': self.API_USERNAME,
            'password': self.API_PASSWORD,
            'messages': [msg],
            'extended_view': 'sms_details',
        }
        # jeśli chcemy zaplanować wysyłkę
        if scheduled_date:
            payload['sch_date'] = scheduled_date.strftime('%Y-%m-%d %H:%M:%S')

        # wywołanie API
        result = self._call_api('send_multi_sms', payload)
        if not result or not result.get('msg_details'):
            _logger.error("Wysyłka SMS nie powiodła się dla numeru %s", phone_number)
            _logger.error(result)
            return False

        return result

    @api.model
    def send_sms_to_number(self, phone_number, message_text, sender_number=None, scheduled_date=None):
        """
        Send a single SMS to the given phone number,
        then immediately poll its delivery status.
        :param phone_number: numer telefonu (string), np. '+48123456789'
        :param message_text: treść wiadomości
        :param sender_number: (opcjonalnie) numer nadawcy
        :param scheduled_date: (opcjonalnie) datetime do zaplanowania wysyłki
        :return: dict ze strukturą {
                    'external_id': <smsid>,
                    'initial_reply': <odpowiedź send_multi_sms>,
                    'delivery_status': <'sent'|'delivered'|'failed'|'scheduled'|'unknown'>
                 } lub False przy błędzie
        """
        if not phone_number:
            _logger.error("Brak numeru telefonu do wysłania SMS")
            return False

        sender = sender_number or self._get_default_sender_number()

        msg = {'destination_number': phone_number, 'text': message_text}
        payload = {
            'username': self.API_USERNAME,
            'password': self.API_PASSWORD,
            'messages': [msg],
            'extended_view': 'sms_details',
        }
        if scheduled_date:
            payload['sch_date'] = scheduled_date.strftime('%Y-%m-%d %H:%M:%S')

        # 1) wyślij SMS
        result = self._call_api('send_multi_sms', payload)
        if not result or not result.get('msg_details'):
            _logger.error("Wysyłka SMS nie powiodła się dla numeru %s", phone_number)
            _logger.error(result)
            return False

        smsid = result['msg_details'][0].get('smsid')
        if not smsid:
            _logger.error("Brak smsid w odpowiedzi API dla numeru %s", phone_number)
            return {'initial_reply': result, 'delivery_status': 'unknown'}

        # 2) od razu poll statusu po konkretnym smsid
        poll_payload = {
            'username': self.API_USERNAME,
            'password': self.API_PASSWORD,
            'messageids': [smsid],
        }
        poll = self._call_api('retrieve_sent_sms_by_ids', poll_payload)
        status = 'unknown'
        if poll and poll.get('messages'):
            info = poll['messages'][0]
            txt = (info.get('status') or '').lower()
            if 'zakończona sukcesem' in txt or 'potwierdziło wysyłkę' in txt:
                status = 'delivered'
            elif 'zakończona błędem' in txt or 'odrzuciło wysyłkę' in txt:
                status = 'failed'
            elif 'zakolejkowan' in txt:
                status = 'scheduled'
            else:
                status = 'sent'

        return {
            'external_id': smsid,
            'initial_reply': result,
            'delivery_status': status,
        }



    def action_send_now(self):
        """Wyślij tę wiadomość przez API i zaktualizuj external_id, sms_gateway_response i state."""
        for msg in self.filtered(lambda m: m.state in ('draft', 'scheduled')):
            # Budowa payload
            payload = {
                'username': self.API_USERNAME,
                'password': self.API_PASSWORD,
                'messages': [{
                    'destination_number': msg.partner_id.phone,
                    'text': msg.body
                }],
                'extended_view': 'sms_details',
            }
            # Wywołanie API
            result = msg._call_api('send_multi_sms', payload)
            _logger.info(result)
            # Obsługa odpowiedzi
            if result and result.get('msg_details'):
                detail = result['msg_details'][0]
                msg.write({
                    'external_id':          detail.get('smsid'),
                    #'sms_gateway_response': detail,
                    'state':                'sent',
                })
            else:
                msg.state = 'failed'

    def retrieve_gateway_response(self):
        """Pobiera finalne informacje o dostarczeniu SMS-ów na podstawie external_id."""
        smsids = [m.external_id for m in self if m.external_id]
        if not smsids:
            return
        payload = {
            'username': self.API_USERNAME,
            'password': self.API_PASSWORD,
            'messageids': smsids,
        }
        res = self._call_api('retrieve_sent_sms_by_ids', payload)
        if not res or not res.get('messages'):
            return
        for info in res['messages']:
            smsid = info.get('smsid')
            msg = self.filtered(lambda m: m.external_id == smsid)
            if msg:
                msg.write({'sms_gateway_response': info})

    def action_schedule(self):
        for msg in self:
            if msg.state == 'draft':
                msg.state = 'scheduled'

    @api.model
    def send_sms_batch(self):
        to_send = self.search([
            ('state', '=', 'scheduled'),
            ('date_scheduled', '<=', fields.Datetime.now())
        ])
        to_send.action_send_now()

    @api.model
    def poll_delivery_status_old(self):
        to_check = self.search([('external_id', '!=', False), ('state', '=', 'sent')])
        for msg in to_check:
            payload = {
                'username': self.API_USERNAME,
                'password': self.API_PASSWORD,
                'criteria': [{'destination_number': msg.partner_id.phone}]
            }
            result = self._call_api('query_sent_messages', payload)
            if result and result.get('messages'):
                info = result['messages'][0]
                status = info.get('status', '')
                if status == 'wysyłka zakończona sukcesem':
                    msg.state = 'delivered'
                elif 'błąd' in status:
                    msg.state = 'failed'

    @api.model
    def poll_delivery_status(self):
        _logger.info("Jestem !!!!!!!!!!!!!")
        to_check = self.search([
            ('external_id', '!=', False),
            ('state', '=', 'sent')
        ])
        for msg in to_check:
            payload = {
                'username': self.API_USERNAME,
                'password': self.API_PASSWORD,
                # Pobieramy zwrot po konkretnym external_id
                'messageids': [msg.external_id],
            }
            try:
                result = self._call_api('retrieve_sent_sms_by_ids', payload)
            except Exception as e:
                _logger.info("Błąd API retrieve_sent_sms_by_ids dla %s: %s", msg.external_id, e)
                continue

            messages = result.get('messages') or []
            if not messages:
                _logger.warning("Brak danych statusu dla SMS %s", msg.external_id)
                continue

            info = messages[0]
            status = (info.get('status') or '').lower()

            # sukces
            if 'zakończona sukcesem' in status or 'potwierdziło wysyłkę' in status:
               # msg.state = 'delivered'
                msg.sms_gateway_response = status
            # błąd
            elif 'zakończona błędem' in status or 'odrzuciło wysyłkę' in status:
                msg.sms_gateway_response = status
            # kolejka
            elif 'zakolejkowan' in status:
                msg.sms_gateway_response = status
            else:
                msg.sms_gateway_response = status
                _logger.info("Nieznany status SMS %s: %s", msg.external_id, status)

