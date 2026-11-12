"""Makes the two keys for phone alerts.  Run once:   py make_vapid_keys.py
Then set VAPID_PUBLIC_KEY and VAPID_PRIVATE_KEY (and VAPID_EMAIL, e.g. mailto:you@gmail.com) in the website's environment.
On your own computer you can put them in PowerShell first:  $env:VAPID_PUBLIC_KEY="..."  etc.   Keep the private key secret."""
import base64

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid


def b64(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


vapid = Vapid()
vapid.generate_keys()
public = vapid.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
print("VAPID_PUBLIC_KEY  =", b64(public))
print("VAPID_PRIVATE_KEY =", b64(private))
print("VAPID_EMAIL       = mailto:your-email@example.com")
