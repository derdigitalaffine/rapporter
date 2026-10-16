from xml.etree import ElementTree as ET

from django.test import SimpleTestCase

from .calendar_subscription_dav import C, D, q, report_properties


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
