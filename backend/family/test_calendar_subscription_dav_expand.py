from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID
from xml.etree import ElementTree as ET

from django.test import RequestFactory, SimpleTestCase

from . import calendar_subscription_dav as dav_module
from .calendar_subscription_dav import C, D, q, query_targets_events, report_properties


class CalDAVReportPropertyTests(SimpleTestCase):
    def test_calendar_data_expand_is_accepted(self):
        prop = ET.fromstring(
            '''<D:prop xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
                <D:getetag/>
                <C:calendar-data>
                    <C:expand start="20261001T000000Z" end="20261101T000000Z"/>
                </C:calendar-data>
            </D:prop>'''
        )

        self.assertEqual(report_properties(prop), [q(D, 'getetag'), q(C, 'calendar-data')])

    def test_calendar_data_component_projection_is_accepted(self):
        prop = ET.fromstring(
            '''<D:prop xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
                <D:getetag/>
                <C:calendar-data content-type="text/calendar" version="2.0">
                    <C:comp name="VCALENDAR">
                        <C:prop name="VERSION"/>
                        <C:comp name="VEVENT">
                            <C:prop name="UID"/>
                            <C:prop name="DTSTART"/>
                            <C:prop name="DTEND" novalue="no"/>
                        </C:comp>
                        <C:comp name="VTIMEZONE"><C:allprop/></C:comp>
                    </C:comp>
                </C:calendar-data>
            </D:prop>'''
        )

        self.assertEqual(report_properties(prop), [q(D, 'getetag'), q(C, 'calendar-data')])

    def test_calendar_data_unknown_nested_selector_is_rejected(self):
        prop = ET.fromstring(
            '''<D:prop xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
                <C:calendar-data><C:unknown-selector/></C:calendar-data>
            </D:prop>'''
        )

        with self.assertRaises(ValueError):
            report_properties(prop)

    def test_calendar_data_expand_requires_valid_ordered_window(self):
        prop = ET.fromstring(
            '''<D:prop xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav">
                <C:calendar-data>
                    <C:expand start="20261101T000000Z" end="20261001T000000Z"/>
                </C:calendar-data>
            </D:prop>'''
        )

        with self.assertRaises(ValueError):
            report_properties(prop)


class CalDAVQueryComponentTests(SimpleTestCase):
    def test_vtodo_query_is_a_valid_empty_match_for_event_only_calendar(self):
        root = ET.fromstring(
            '''<C:calendar-query xmlns:C="urn:ietf:params:xml:ns:caldav" xmlns:D="DAV:">
                <D:prop><D:getetag/><C:calendar-data/></D:prop>
                <C:filter>
                    <C:comp-filter name="VCALENDAR">
                        <C:comp-filter name="VTODO">
                            <C:prop-filter name="COMPLETED"><C:is-not-defined/></C:prop-filter>
                            <C:prop-filter name="STATUS">
                                <C:text-match negate-condition="yes">CANCELLED</C:text-match>
                            </C:prop-filter>
                        </C:comp-filter>
                    </C:comp-filter>
                </C:filter>
            </C:calendar-query>'''
        )

        self.assertFalse(query_targets_events(root))

    def test_vevent_query_still_targets_event_resources(self):
        root = ET.fromstring(
            '''<C:calendar-query xmlns:C="urn:ietf:params:xml:ns:caldav">
                <C:filter>
                    <C:comp-filter name="VCALENDAR">
                        <C:comp-filter name="VEVENT"/>
                    </C:comp-filter>
                </C:filter>
            </C:calendar-query>'''
        )

        self.assertTrue(query_targets_events(root))


class CalDAVEndpointCompatibilityTests(SimpleTestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.grant = SimpleNamespace(pk=UUID('3ad46710-b348-41a9-aeb8-94568c12c532'))
        self.path = f'{self.grant.pk}/home/family/'
        self.url = f'/caldav/{self.path}'

    def _report(self, body):
        request = self.factory.generic(
            'REPORT',
            self.url,
            data=body.encode('utf-8'),
            content_type='application/xml; charset=utf-8',
            HTTP_DEPTH='1',
        )
        with (
            patch.object(dav_module, 'limited', return_value=None),
            patch.object(dav_module, 'authenticate', return_value=self.grant),
            patch.object(dav_module, 'shared_events', return_value=[]),
        ):
            return dav_module.dav(request, path=self.path)

    def test_vtodo_report_returns_empty_multistatus_instead_of_error(self):
        response = self._report(
            '''<C:calendar-query xmlns:C="urn:ietf:params:xml:ns:caldav" xmlns:D="DAV:">
                <D:prop><D:getetag/><C:calendar-data/></D:prop>
                <C:filter>
                    <C:comp-filter name="VCALENDAR">
                        <C:comp-filter name="VTODO">
                            <C:prop-filter name="COMPLETED"><C:is-not-defined/></C:prop-filter>
                            <C:prop-filter name="STATUS">
                                <C:text-match negate-condition="yes">CANCELLED</C:text-match>
                            </C:prop-filter>
                        </C:comp-filter>
                    </C:comp-filter>
                </C:filter>
            </C:calendar-query>'''
        )

        self.assertEqual(response.status_code, 207)
        root = ET.fromstring(response.content)
        self.assertEqual(root.tag, q(D, 'multistatus'))
        self.assertEqual(root.findall(q(D, 'response')), [])

    def test_calendar_data_projection_report_reaches_multistatus_response(self):
        response = self._report(
            '''<C:calendar-query xmlns:C="urn:ietf:params:xml:ns:caldav" xmlns:D="DAV:">
                <D:prop>
                    <D:getetag/>
                    <C:calendar-data content-type="text/calendar" version="2.0">
                        <C:comp name="VCALENDAR">
                            <C:prop name="VERSION"/>
                            <C:comp name="VEVENT"><C:prop name="UID"/></C:comp>
                        </C:comp>
                    </C:calendar-data>
                </D:prop>
                <C:filter>
                    <C:comp-filter name="VCALENDAR"><C:comp-filter name="VEVENT"/></C:comp-filter>
                </C:filter>
            </C:calendar-query>'''
        )

        self.assertEqual(response.status_code, 207)
        self.assertEqual(ET.fromstring(response.content).tag, q(D, 'multistatus'))
