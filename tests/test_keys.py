import base64
import shutil
import subprocess
import unittest

from neuvpn import keys


class X25519Test(unittest.TestCase):
    # RFC 7748, section 5.2 and 6.1
    def test_rfc7748_vectors(self):
        vectors = [
            (
                "a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4",
                "e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c",
                "c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552",
            ),
            (
                "4b66e9d4d1b4673c5ad22691957d6af5c11b6421e0ea01d42ca4169e7918ba0d",
                "e5210f12786811d3f4b7959d0538ae2c31dbe7106fc03c3efc4cd549c715a493",
                "95cbde9476e8907d7aade45cb4b873f88b595a68799fa152e6f8f7647aac7957",
            ),
        ]
        for scalar, u, out in vectors:
            self.assertEqual(keys.x25519(bytes.fromhex(scalar), bytes.fromhex(u)).hex(), out)

    def test_rfc7748_diffie_hellman(self):
        alice = bytes.fromhex("77076d0a7318a57d3c16c17251b26645df4c2f87ebc0992ab177fba51db92c2a")
        bob = bytes.fromhex("5dab087e624a8a4b79e17f8b83800ee66f3bb1292618b6fd1c2f8b27ff88e0eb")
        alice_pub = base64.b64decode(keys.public_key(base64.b64encode(alice).decode()))
        bob_pub = base64.b64decode(keys.public_key(base64.b64encode(bob).decode()))
        self.assertEqual(alice_pub.hex(), "8520f0098930a754748b7ddcb43ef75a0dbf3a0d26381af4eba4a98eaa9b4e6a")
        self.assertEqual(bob_pub.hex(), "de9edb7d7b7dc1b4d35b61c2ece435373f8343c85b78674dadfc7e146f882b4f")
        shared = "4a5d9d5ba4ce2de1728e3bf480350f25e07e21c947d19e3376f09b3c1e161742"
        self.assertEqual(keys.x25519(alice, bob_pub).hex(), shared)
        self.assertEqual(keys.x25519(bob, alice_pub).hex(), shared)

    def test_generated_keys_are_valid_and_unique(self):
        pairs = {keys.generate_keypair() for _ in range(5)}
        self.assertEqual(len(pairs), 5)
        for priv, pub in pairs:
            self.assertTrue(keys.is_valid_key(priv))
            self.assertTrue(keys.is_valid_key(pub))
            raw = base64.b64decode(priv)
            self.assertEqual(raw[0] & 7, 0)
            self.assertEqual(raw[31] & 0xC0, 0x40)
        self.assertTrue(keys.is_valid_key(keys.generate_preshared_key()))
        self.assertFalse(keys.is_valid_key("not-a-key"))

    @unittest.skipUnless(shutil.which("wg"), "wireguard-tools not installed")
    def test_matches_wg_pubkey(self):
        priv, pub = keys.generate_keypair()
        out = subprocess.run(["wg", "pubkey"], input=priv.encode(), capture_output=True, check=True)
        self.assertEqual(out.stdout.decode().strip(), pub)


if __name__ == "__main__":
    unittest.main()
