import unittest
from report import generate_invoice_html

class TestInvoiceAdditionalPayments(unittest.TestCase):
    def test_additional_payments_rendering(self):
        billing_data = {
            "counted_seconds": 3600,
            "total_earned": 50.0,
            "session_count": 1,
            "project_breakdown": [
                {
                    "project": "Development",
                    "seconds": 3600,
                    "formatted": "1h 00m 00s",
                    "earned_display": "$50.00",
                    "color": "#4F46E5",
                }
            ],
        }
        settings_data = {
            "hourly_rate": 50.0,
            "currency_symbol": "$",
            "business_name": "Test Company",
        }

        additional_items = [
            {"description": "Setup Fee & Consulting", "amount": 100.0}
        ]

        html = generate_invoice_html(
            billing_data,
            settings_data,
            status="unpaid",
            invoice_no="INV-100",
            additional_items=additional_items,
        )

        self.assertIn("Setup Fee &amp; Consulting", html)
        self.assertIn("$150.00", html) # Total: $50 base + $100 fee

if __name__ == "__main__":
    unittest.main()
