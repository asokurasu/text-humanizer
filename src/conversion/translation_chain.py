from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Tuple, List, Union, Any

import re
import struct
import hashlib
from abc import ABC, abstractmethod
from base64 import b64encode, b64decode
from typing import Optional, List, Tuple, Union, cast
from base58check import b58encode, b58decode  # type: ignore
from ecdsa import (  # type: ignore
    SigningKey,
    VerifyingKey,
    SECP256k1,
    numbertheory,
    ellipticcurve,
)
from ecdsa.util import sigencode_string, sigdecode_string, sigencode_der  # type: ignore
from sympy.ntheory import sqrt_mod  # type: ignore

from bitcoinutils.constants import (
    NETWORK_WIF_PREFIXES,
    NETWORK_P2PKH_PREFIXES,
    NETWORK_P2SH_PREFIXES,
    SIGHASH_ALL,
    P2PKH_ADDRESS,
    P2SH_ADDRESS,
    P2WPKH_ADDRESS_V0,
    P2WSH_ADDRESS_V0,
    P2TR_ADDRESS_V1,
    NETWORK_SEGWIT_PREFIXES,
    TAPROOT_SIGHASH_ALL,
)
from bitcoinutils.setup import get_network
from bitcoinutils.ripemd160 import ripemd160
from bitcoinutils.schnorr import schnorr_sign
from bitcoinutils.transactions import Transaction
from bitcoinutils.utils import (
    Secp256k1Params,
    calculate_tweak,
    add_magic_prefix,
    h_to_i,
    b_to_h,
    h_to_b,
    b_to_i,
    i_to_b32,
    tweak_taproot_pubkey,
    tweak_taproot_privkey,
)
from bitcoinutils.script import Script


import bitcoinutils.bech32


class PrivateKey:
    """Represents an ECDSA private key.

    Attributes
    ----------
    key : bytes
        the raw key of 32 bytes

    Methods
    -------
    from_wif(wif)
        creates an object from a WIF of WIFC format (string)
    from_bytes()
        creates an object from raw 32 bytes
    to_wif(compressed=True)
        returns as WIFC (compressed) or WIF format (string)
    to_bytes()
        returns the key's raw bytes
    sign_message(message, compressed=True)
        signs the message's digest and returns the signature
    sign_input(tx, txin_index, script, sighash=SIGHASH_ALL)
        creates the transaction's digest and signs it for a particular index
        and returns the signature.
    sign_segwit_input(tx, txin_index, script, amount, sighash=SIGHASH_ALL)
        creates the transaction's digest and signs it for a particular index
        and amount and returns the signature.
    sign_taproot_input(tx, txin_index, utxo_scripts, amounts, script_path=False,
                       script=None, sighash=TAPROOT_SIGHASH_ALL, tweak=True)
        creates the transaction's digest and signs it for a particular index
        input script_pub_keys and amounts and returns the signature. By default
        it tweaks the keys but it can be disabled for tapleaf scripts.
    get_public_key()
        returns the corresponding PublicKey object
    """

    def __init__(
        self,
        wif: Optional[str] = None,
        secret_exponent: Optional[int] = None,
        b: Optional[bytes] = None,
    ) -> None:
        """With no parameters a random key is created

        Parameters
        ----------
        wif : str, optional
            the key in WIF of WIFC format (default None)
        secret_exponent : int, optional
            used to create a specific key deterministically (default None)
        b : bytes, optional
            used to create a key from raw bytes
        """

        if not secret_exponent and not wif and not b:
            self.key = SigningKey.generate(curve=SECP256k1)
        else:
            if wif:
                self._from_wif(wif)
            elif b:
                self._from_bytes(b)
            elif secret_exponent:
                self.key = SigningKey.from_secret_exponent(
                    secret_exponent, curve=SECP256k1
                )

    def to_bytes(self) -> bytes:
        """Returns key's bytes"""

        return self.key.to_string()

    @classmethod
    def from_wif(cls, wif: str) -> 'PrivateKey':
        """Creates key from WIFC or WIF format key"""

        return cls(wif=wif)

    @classmethod
    def from_bytes(cls, b: bytes) -> 'PrivateKey':
        """Creates a key directly from 32 raw bytes"""

        return cls(b=b)

    def _from_bytes(self, b: bytes) -> None:
        """Creates a key directly from 32 raw bytes"""

        if len(b) != 32:
            raise ValueError("Invalid key length: must be exactly 32 bytes.")
        self.key = SigningKey.from_string(b, curve=SECP256k1)

    # expects wif in hex string
    def _from_wif(self, wif: str) -> None:
        """Creates key from WIFC or WIF format key

        Check to_wif for the detailed process. From WIF is the reverse.

        Raises
        ------
        ValueError
            if the checksum is wrong or if the WIF/WIFC is not from the
            configured network.
        """

        wif_utf = wif.encode("utf-8")

        # decode base58check get key bytes plus checksum
        data_bytes = b58decode(wif_utf)
        key_bytes = data_bytes[:-4]
        checksum = data_bytes[-4:]

        # verify key with checksum
        data_hash = hashlib.sha256(hashlib.sha256(key_bytes).digest()).digest()
        if not checksum == data_hash[0:4]:
            raise ValueError("Checksum is wrong. Possible mistype?")

        # get network prefix and check with current setup
        network_prefix = key_bytes[:1]
        if NETWORK_WIF_PREFIXES[get_network()] != network_prefix:
            raise ValueError("Using the wrong network!")

        # remove network prefix
        key_bytes = key_bytes[1:]

        # check length of bytes and if > 32 then compressed
        # use this to instantite an ecdsa key
        if len(key_bytes) > 32:
            self.key = SigningKey.from_string(key_bytes[:-1], curve=SECP256k1)
        else:
            self.key = SigningKey.from_string(key_bytes, curve=SECP256k1)

    def to_wif(self, compressed: bool = True) -> str:
        """Returns key in WIFC or WIF string

        |  Pseudocode:
        |      network_prefix = (1 byte version number)
        |      data = network_prefix + (32 bytes number/key) [ + 0x01 if compressed ]
        |      data_hash = SHA-256( SHA-256( data ) )
        |      checksum = (first 4 bytes of data_hash)
        |      wif = Base58CheckEncode( data + checksum )
        """

        # add network prefix to the key
        data = NETWORK_WIF_PREFIXES[get_network()] + self.to_bytes()

        if compressed is True:
            data += b"\x01"

        # double hash and get the first 4 bytes for checksum
        data_hash = hashlib.sha256(hashlib.sha256(data).digest()).digest()
        checksum = data_hash[0:4]

        # suffix the key bytes with the checksum and encode to base58check
        wif = b58encode(data + checksum)

        return wif.decode("utf-8")

    def sign_message(self, message: str, compressed: bool = True) -> Optional[str]:
        """Signs the message with the private key (deterministically)

        Bitcoin uses a compact format for message signatures (for tx sigs it
        uses normal DER format). The format has the normal r and s parameters
        that ECDSA signatures have but also includes a prefix which encodes
        extra information. Using the prefix the public key can be
        reconstructed when verifying the signature.

        |  Prefix values:
        |      27 - 0x1B = first key with even y
        |      28 - 0x1C = first key with odd y
        |      29 - 0x1D = second key with even y
        |      30 - 0x1E = second key with odd y

        If key is compressed add 4 (31 - 0x1F, 32 - 0x20, 33 - 0x21, 34 - 0x22
        respectively)

        Returns a Bitcoin compact signature in Base64
        """

        # All bitcoin signatures include the magic prefix. It is just a string
        # added to the message to distinguish Bitcoin-specific messages.
        message_magic = add_magic_prefix(message)

        # create message digest -- note double hashing
        message_digest = hashlib.sha256(hashlib.sha256(message_magic).digest()).digest()

        #
        # sign non-deterministically - no reason
        # signature = self.key.sign_digest(message_digest,
        #                                 sigencode=sigencode_string)

        # deterministic signing
        signature = self.key.sign_digest_deterministic(
            message_digest, sigencode=sigencode_string, hashfunc=hashlib.sha256
        )
        prefix = 27
        if compressed:
            prefix += 4

        address = self.get_public_key().get_address(compressed=compressed).to_string()
        for i in range(prefix, prefix + 4):
            recid = chr(i).encode("utf-8")
            sig = b64encode(recid + signature).decode("utf-8")
            try:
                if PublicKey.verify_message(address, sig, message):
                    return sig
            except ValueError:
                continue

        return None

    def sign_input(
        self, tx: Transaction, txin_index: int, script: Script, sighash: int = SIGHASH_ALL
    ) -> str:
        # get the digest from the transaction object and sign
        tx_digest = tx.get_transaction_digest(txin_index, script, sighash)
        return self._sign_input(tx_digest, sighash)

    def sign_segwit_input(
        self,
        tx: Transaction,
        txin_index: int,
        script: Script,
        amount: int,
        sighash: int = SIGHASH_ALL,
    ) -> str:
        # get the digest from the transaction object and sign
        tx_digest = tx.get_transaction_segwit_digest(
            txin_index, script, amount, sighash
        )
        return self._sign_input(tx_digest, sighash)

    def sign_taproot_input(
        self,
        tx: Transaction,
        txin_index: int,
        utxo_scripts: list[Script],
        amounts: list[int],
        script_path: bool = False,
        tapleaf_script: Script = Script([]),
        tapleaf_scripts: Optional[Union[Script, List[Script], List[List[Script]], bytes]] = None,
        sighash: int = TAPROOT_SIGHASH_ALL,
        tweak: bool = True,
    ) -> str:
        # get the digest from the transaction object and sign
        # note that when signing a tapleaf we typically won't use tweaked
        # keys - so tweak should be set to False
        if script_path:
            tx_digest = tx.get_transaction_taproot_digest(
                txin_index,
                utxo_scripts,
                amounts,
                1,
                script=tapleaf_script,
                sighash=sighash,
            )
        else:
            tx_digest = tx.get_transaction_taproot_digest(
                txin_index, utxo_scripts, amounts, 0, sighash=sighash
            )
        return self._sign_taproot_input(tx_digest, sighash, tapleaf_scripts, tweak)

    def _sign_input(self, tx_digest: bytes, sighash: int = SIGHASH_ALL) -> str:
        """Signs a transaction input with the private key

        Bitcoin uses the normal DER format for transactions. Each input is
        signed separately (thus txin_index is required). The script of the
        input we wish to spend is required and replaces the transaction's
        script sig in order to calculate the correct transaction hash (which
        is what is actually signed!)

        Returns a signature for that input
        """

        # Both R ans S cannot start with 0x00 (be signed as negative) unless
        # they are higher than 2^128 or start with 0x80.
        #
        # From Bitcoin core v0.17 a Low R value is required. This way
        # signatures are always 71 bytes. Because R is not mutable in the same
        # way that S is, a low R value can only be found by trying different
        # nonces (RFC6979 - deterministic nonce generation).
        #
        # https://bitcoin.stackexchange.com/questions/88702/why-is-a-librarys-
        # signature-of-a-segwit-tx-different-from-bitcoin-core-signatur
        #
        # For this reason we test if we get a Low R value (should be <0x80 and
        # thus not have the 0x00 prefix that specifies a negative signed
        # number) we need to change the entropy by using extra_entropy and re-sign
        # until we get a Low R value.

        # sign - note that deterministic signing is used
        signature = self.key.sign_digest_deterministic(
            tx_digest, sigencode=sigencode_der, hashfunc=hashlib.sha256
        )

        # if high R re-sign until we get a low R value
        # if high R then its size will be 33 bytes to include the sign
        attempt = 1
        length_r = signature[3]
        while length_r == 33:
            signature = self.key.sign_digest_deterministic(
                tx_digest,
                extra_entropy=i_to_b32(attempt),
                sigencode=sigencode_der,
                hashfunc=hashlib.sha256,
            )
            attempt += 1
            length_r = signature[3]

        # make sure that signature complies with Low S standardness rule of
        # BIP62: https://github.com/bitcoin/bips/blob/master/bip-0062.mediawiki
        #
        # The S part of the signature is equivalent to (order-S). This allows
        # for txid malleability attacks where S is modified with (order-S) and
        # thus a valid signature... but the txid hash would be different!
        #
        # For this reason Low S standardness rule specifies that all S's need
        # to be less than half of the curve order (SECP256k1). If it is not we
        # ensure it is by substrituting it with (order-S).

        # get DER values individually -- DER structure is:
        #   1-byte   -- 0x30 to specify a DER compound object (R,S)
        #   1-byte   -- length of the compound object
        #   1-byte   -- 0x02 to specify integer type for R
        #   1-byte   -- length of signature's R value
        #   variable -- R value
        #   1-byte   -- 0x02 to specify integer type for S
        #   1-byte   -- length of signature's S value
        #   variable -- S value

        der_prefix = signature[0]
        length_total = signature[1]
        der_type_int = signature[2]
        length_r = signature[3]
        R = signature[4 : 4 + length_r]
        length_s = signature[5 + length_r]
        S = signature[5 + length_r + 1 :]
        S_as_bigint = b_to_i(S)

        # update S -- Low S standardness rule

        # if length is 33 bytes then it contains a sign and thus is high S
        if length_s == 33:
            new_S_as_bigint = Secp256k1Params._order - S_as_bigint
            # convert bigint to bytes
            # new_S = h_to_b(i_to_h64(new_S_as_bigint))
            new_S = i_to_b32(new_S_as_bigint)
            # new value should be 32 bytes
            assert len(new_S) == 0x20
            # reduce appropriate lengths
            length_s -= 1
            length_total -= 1
        else:
            new_S = S

        # reconstruct signature
        signature = (
            struct.pack("BBBB", der_prefix, length_total, der_type_int, length_r)
            + R
            + struct.pack("BB", der_type_int, length_s)
            + new_S
        )

        # add sighash in the signature -- as one byte!
        signature += struct.pack("B", sighash)

        # note that this is the final sig that needs to be added in the
        # script_sig (i.e. the DER signature plus the sighash)
        return b_to_h(signature)

    # TODO add all_scripts to proper tweaking
    def _sign_taproot_input(
        self,
        tx_digest: bytes,
        sighash: int = SIGHASH_ALL,
        scripts: Optional[Union[Script, List[Script], List[List[Script]], bytes]] = None,
        tweak: bool = True,
    ) -> str:
        """Signs a taproot transaction input with the private key

        Taproot uses Schnorr signatures. The format is just R and S so only
        64 bytes. If SIGHASH_ALL then nothing is included (i.e. default).
        If another sighash then it is included in the end (65 bytes).

        Note that when signing for script path (tapleafs) we typically won't
        use tweaking so tweak should be set to False

        Returns a signature for that input
        """

        byte_key = b""

        if tweak:
            tweak_int = calculate_tweak(self.get_public_key(), scripts)
            byte_key = tweak_taproot_privkey(self.key.to_string(), tweak_int)
        else:
            # negating the private key is not necessary since the schnorr lib
            # is handling it
            # negated_key = self.get_negated_key()
            # byte_key = bytes.fromhex(negated_key)
            byte_key = self.key.to_string()

        # a value in rand_aux will make the signatures different from bitcoin core
        # if rand_aux is None:
        #     rand_aux = hashlib.sha256(tx_digest + byte_key).digest()

        # Currently bitcoin core is just passing 32 bytes data as randam aux
        # https://github.com/bitcoin/bitcoin/blob/master/src/script/sign.cpp#L88
        rand_aux = bytes(32)

        # use BIP-340 python's reference implementation for signing
        sig = schnorr_sign(tx_digest, byte_key, rand_aux)

        # 65 bytes if sighash is not TAPROOT_SIGHASH_ALL
        if sighash != TAPROOT_SIGHASH_ALL:
            sig += sighash.to_bytes(1, "big")

        return b_to_h(sig)

    def get_public_key(self) -> 'PublicKey':
        """Returns the corresponding PublicKey"""

        verifying_key = b_to_h(self.key.get_verifying_key().to_string())
        return PublicKey("04" + verifying_key)


class PublicKey:
    """Represents an ECDSA public key.

    Attributes
    ----------
    key : bytes
        the raw public key of 64 bytes (x, y coordinates of the ECDSA curve)

    Methods
    -------
    from_hex(hex_str)
        creates an object from a hex string in SEC format (classmethod)
    from_message_signature(signature)
        NO-OP! (classmethod)
    verify_message(address, signature, message) (classmethod)
        constructs the public key, confirms the address and
        verifies the signature (classmethod)
    verify(signature, message)
        returns true if the message was signed with this public key's
        corresponding private key.
    to_hex(compressed=True)
        returns the key as hex string (in SEC format - compressed by default)
    to_x_only_hex(script)
        returns the x coordinate only as hex string before tweaking (needed for taproot)
    to_taproot_hex(script)
        returns the x coordinate only as hex string after tweaking (needed for taproot)
    is_y_even()
        returns true if y coordinate is even
    to_bytes()
        returns the key's raw bytes
    to_hash160()
        returns the hash160 hex string of the public key
    get_address(compressed=True))
        returns the corresponding P2pkhAddress object
    get_segwit_address()
        returns the corresponding P2wpkhAddress object
    get_taproot_address(scripts)
        returns the corresponding P2trAddress object
    """

    def __init__(self, hex_str: Optional[str] = None, message: Optional[str] = None, signature: Optional[bytes] = None) -> None:
        """
        Parameters
        ----------
        hex_str : str, optional
            the public key in hex string

        In case of generating public key from message and signature:-
        message : str, optional
            The original message that was signed
        signature : bytes, optional
            A 65-byte Bitcoin signature (1-byte recovery ID + 64-byte ECDSA signature).

        Raises
        ------
        TypeError
            If first byte of public key (corresponding to SEC format) is
            invalid.
            If neither hex_str nor (message, signature) are provided
        ValueError
            If message is empty when attempting recovery
            If signature is not exactly 65 bytes
            If an invalid recovery ID is detected
        """
        if hex_str:
            hex_str = hex_str.strip()

            # Normalize hex string by removing '0x' prefix and any whitespace
            if hex_str.lower().startswith('0x'):
                hex_str = hex_str[2:]

            # expects key as hex string - SEC format
            first_byte_in_hex = hex_str[:2]  # 2 hex chars = 1 byte
            hex_bytes = h_to_b(hex_str)

            taproot = False

            # check if compressed or not
            if len(hex_bytes) > 33:
                # uncompressed - SEC format: 0x04 + x + y coordinates (x,y are 32 byte
                # numbers)

                # remove first byte and instantiate ecdsa key
                self.key = VerifyingKey.from_string(hex_bytes[1:], curve=SECP256k1)
            elif len(hex_bytes) > 31:
                # key is either compressed or in x-only taproot format

                # taproot public keys are exactly 32 bytes
                if len(hex_bytes) == 32:
                    taproot = True

                # compressed - SEC FORMAT: 0x02|0x03 + x coordinate (if 02 then y
                # is even else y is odd. Calculate y and then instantiate the ecdsa key
                x_coord = int(hex_str if taproot else hex_str[2:], 16)

                # y = modulo_square_root( (x**3 + 7) mod p ) -- there will be 2 y values
                y_values = sqrt_mod(
                    (x_coord**3 + 7) % Secp256k1Params._p, Secp256k1Params._p, True
                )

                assert y_values is not None
                # check SEC format's first byte to determine which of the 2 values to use
                if first_byte_in_hex == "02" or taproot:
                    # y is the even value
                    if y_values[0] % 2 == 0:  # type: ignore
                        y_coord = y_values[0]  # type: ignore
                    else:
                        y_coord = y_values[1]  # type: ignore
                elif first_byte_in_hex == "03":
                    # y is the odd value
                    if y_values[0] % 2 == 0:  # type: ignore
                        y_coord = y_values[1]  # type: ignore
                    else:
                        y_coord = y_values[0]  # type: ignore
                else:
                    raise TypeError("Invalid SEC compressed format")

                uncompressed_hex = f"{x_coord:064x}{y_coord:064x}"
                uncompressed_hex_bytes = h_to_b(uncompressed_hex)
                self.key = VerifyingKey.from_string(uncompressed_hex_bytes, curve=SECP256k1)
        elif message or signature:
            if not message:
                raise ValueError("Empty message provided for public key recovery.")

            if not signature or len(signature) != 65:
                raise ValueError("Invalid signature length, must be exactly 65 bytes")

            # The compressed signature is of the format: recovery_id (1 byte) | r (32 bytes) | s (32 bytes)
            # We subtract the prefix(27) for uncompressed signatures and an additional 4 (31) for compressed signatures to get the recovery id
            recovery_id = signature[0] - 31
            if not (0 <= recovery_id <= 3): # A valid recovery ID is between 0 and 3
                raise ValueError(f"Invalid recovery ID: expected 31-34, got {signature[0]}")

            signature = signature[1:] #Remove recovery id from signature

            # All bitcoin signatures include the magic prefix. It is just a string
            # added to the message to distinguish Bitcoin-specific messages.
            message_magic = add_magic_prefix(message)
            # create message digest
            message_digest = hashlib.sha256(hashlib.sha256(message_magic).digest()).digest()

            recovered_keys = VerifyingKey.from_public_key_recovery_with_digest(
                signature, message_digest, curve=SECP256k1, hashfunc = hashlib.sha256, sigdecode=sigdecode_string
            )
            self.key = recovered_keys[recovery_id]
        else:
            raise TypeError("Either 'hex_str' or ('message', 'signature') must be provided.")

    @classmethod
    def from_hex(cls, hex_str: str) -> 'PublicKey':
        """Creates a public key from a hex string (SEC format)"""

        return cls(hex_str)

    def to_bytes(self) -> bytes:
        """Returns key's bytes"""

        return self.key.to_string()

    def to_hex(self, compressed: bool = True) -> str:
        """Returns public key as a hex string (SEC format - compressed by
        default)"""

        key_hex = b_to_h(self.key.to_string())

        if compressed:
            # check if y is even or odd (02 even, 03 odd)
            if h_to_i(key_hex[-2:]) % 2 == 0:
                key_str = "02" + key_hex[:64]
            else:
                key_str = "03" + key_hex[:64]
        else:
            # uncompressed starts with 04
            key_str = "04" + key_hex

        return key_str

    def to_x_only_hex(self) -> str:
        """Returns the x coordinate of the public key as hex string."""

        key_hex = self.key.to_string().hex()
        return key_hex[:64]

    def to_taproot_hex(
        self, scripts: Optional[Union[Script, List[Script], List[List[Script]]]] = None
    ) -> Tuple[str, bool]:
        """Returns the tweaked x coordinate of the public key as a hex string.

        Parameters
        ==========
        scripts : list[ list[Script] ]
            a list of list of Scripts describing the merkle tree of scripts to commit
        """

        # Tweak public key (BIP340)
        # https://bitcoin.stackexchange.com/a/116391/31844
        tweak_int = calculate_tweak(self, scripts)

        # keep x-only coordinate
        tweak_and_odd = tweak_taproot_pubkey(self.key.to_string(), tweak_int)
        pubkey = tweak_and_odd[0][:32]
        is_odd = tweak_and_odd[1]

        return pubkey.hex(), is_odd

    def is_y_even(self) -> bool:
        """Returns True if the y coordinate of the public key is even and
        False otherwise."""

        key_hex = self.key.to_string().hex()

        y = h_to_i(key_hex[64:])

        return y % 2 == 0

    @classmethod
    def from_message_signature(cls, message: str, signature: bytes) -> 'PublicKey':
        """Recovers a public key from a Bitcoin-signed message and a 65-byte compressed signature.
        """
        #Note: Only works for compressed signatures because DER encoding does not contain the recovery id
        return cls(message=message, signature=signature)
        # raise BaseException("NO-OP!")

    @classmethod
    def verify_message(cls, address: str, signature: str, message: str) -> bool:
        """Creates a public key from a message signature and verifies message

        Bitcoin uses a compact format for message signatures (for tx sigs it
        uses normal DER format). The format has the normal r and s parameters
        that ECDSA signatures have but also includes a prefix which encodes
        extra information. Using the prefix the public key can be
        reconstructed from the signature.

        |  Prefix values:
        |      27 - 0x1B = first key with even y
        |      28 - 0x1C = first key with odd y
        |      29 - 0x1D = second key with even y
        |      30 - 0x1E = second key with odd y

        If key is compressed add 4 (31 - 0x1F, 32 - 0x20, 33 - 0x21,
        34 - 0x22 respectively)

        Raises
        ------
        ValueError
            If signature is invalid
        """

        sig = b64decode(signature.encode("utf-8"))
        if len(sig) != 65:
            raise ValueError("Invalid signature size")

        # get signature prefix, compressed and recid (which key is odd/even)
        prefix = sig[0]
        if prefix < 27 or prefix > 35:
            return False
        if prefix >= 31:
            compressed = True
            recid = prefix - 31
        else:
            compressed = False
            recid = prefix - 27

        # create message digest -- note double hashing
        message_magic = add_magic_prefix(message)
        message_digest = hashlib.sha256(hashlib.sha256(message_magic).digest()).digest()

        #
        # use recid, r and s to get the point in the curve
        #

        # get signature's r and s
        r, s = sigdecode_string(sig[1:], Secp256k1Params._order)

        # ger R's x coordinate
        x = r + (recid // 2) * Secp256k1Params._order

        # get R's y coordinate (y**2 = x**3 + 7)
        y_values = sqrt_mod((x**3 + 7) % Secp256k1Params._p, Secp256k1Params._p, True)
        if (y_values[0] - recid) % 2 == 0:  # type: ignore
            y = y_values[0]  # type: ignore
        else:
            y = y_values[1]  # type: ignore

        # get R (recovered ephemeral key) from x,y
        R = ellipticcurve.Point(Secp256k1Params._curve, x, y, Secp256k1Params._order)

        # get e (encoded message hash as big integer)
        e = b_to_i(message_digest)

        # compute public key Q = r^-1 (sR - eG)
        # because Point substraction is not defined we will instead use:
        # Q = r^-1 (sR + (-eG) )
        minus_e = -e % Secp256k1Params._order
        inv_r = numbertheory.inverse_mod(r, Secp256k1Params._order)
        Q = inv_r * (s * R + minus_e * Secp256k1Params._G)

        # instantiate the public key and verify message
        public_key = VerifyingKey.from_public_point(Q, curve=SECP256k1)
        key_hex = b_to_h(public_key.to_string())
        pubkey = PublicKey.from_hex("04" + key_hex)
        if not pubkey.verify(signature, message):
            return False

        # confirm that the address provided corresponds to that public key
        if pubkey.get_address(compressed=compressed).to_string() != address:
            return False

        return True

    def verify(self, signature: str, message: str) -> bool:
        """Verifies that the message was signed with this public key's
        corresponding private key."""

        # All bitcoin signatures include the magic prefix. It is just a string
        # added to the message to distinguish Bitcoin-specific messages.
        message_magic = add_magic_prefix(message)

        # create message digest -- note double hashing
        message_digest = hashlib.sha256(hashlib.sha256(message_magic).digest()).digest()

        signature_bytes = b64decode(signature.encode("utf-8"))

        # verify -- ignore first byte of compact signature
        return self.key.verify_digest(
            signature_bytes[1:], message_digest, sigdecode=sigdecode_string
        )

    def _to_hash160(self, compressed: bool = True) -> bytes:
        """Returns the RIPEMD( SHA256( ) ) of the public key in bytes"""

        pubkey = h_to_b(self.to_hex(compressed))
        hashsha256 = hashlib.sha256(pubkey).digest()
        hash160 = ripemd160(hashsha256)
        return hash160

    def to_hash160(self, compressed: bool = True) -> str:
        """Returns the RIPEMD( SHA256( ) ) of the public key in hex"""

        return b_to_h(self._to_hash160(compressed))

    def get_address(self, compressed: bool = True) -> 'P2pkhAddress':
        """Returns the corresponding P2PKH Address (default compressed)"""

        hash160 = self._to_hash160(compressed)
        addr_string_hex = b_to_h(hash160)
        return P2pkhAddress(hash160=addr_string_hex)

    def get_segwit_address(self) -> 'P2wpkhAddress':
        """Returns the corresponding P2WPKH address

        Only compressed is allowed. It is otherwise identical to normal P2PKH
        address.
        """
        hash160 = self._to_hash160(True)
        addr_string_hex = b_to_h(hash160)
        return P2wpkhAddress(witness_program=addr_string_hex)

    def get_taproot_address(
        self, scripts: Optional[Union[Script, List[Script], List[List[Script]], bytes]] = None
    ) -> 'P2trAddress':
        """Returns the corresponding P2TR address

        Only compressed is allowed. Taproot uses x-only public key with
        even y (02 compressed keys). By default tagged_hashes are used.

        scripts contains the list of lists of Scripts describing the merkle
        tree
        """

        pubkey_and_is_odd = self.to_taproot_hex(scripts)
        pubkey = pubkey_and_is_odd[0]
        is_odd = pubkey_and_is_odd[1]

        return P2trAddress(witness_program=pubkey, is_odd=is_odd)


class Address(ABC):
    """Represents a Bitcoin address

    Attributes
    ----------
    hash160 : str
        the hash160 string representation of the address; hash160 represents
        two consequtive hashes of the public key or the redeam script, first
        a SHA-256 and then an RIPEMD-160

    Methods
    -------
    from_address(address)
        instantiates an object from address string encoding
    from_hash160(hash160_str)
        instantiates an object from a hash160 hex string
    from_script(redeem_script)
        instantiates an object from a redeem_script
    to_string()
        returns the address's string encoding
    to_hash160()
        returns the address's hash160 hex string representation

    Raises
    ------
    TypeError
        No parameters passed
    ValueError
        If an invalid address or hash160 is provided.
    """

    @abstractmethod
    def __init__(
        self,
        address: Optional[str] = None,
        hash160: Optional[str] = None,
        script: Optional[Script] = None,
    ) -> None:
        """
        Parameters
        ----------
        address : str
            the address as a string
        hash160 : str
            the hash160 hex string representation
        script : Script object
            instantiates an Address object from a redeem script

        Raises
        ------
        TypeError
            No parameters passed
        ValueError
            If an invalid address or hash160 is provided.
        """

        if hash160:
            if self._is_hash160_valid(hash160):
                self.hash160 = hash160
            else:
                raise ValueError("Invalid value for parameter hash160.")
        elif address:
            if self._is_address_valid(address):
                self.hash160 = self._address_to_hash160(address)
            else:
                raise ValueError("Invalid value for parameter address.")
        elif script:
            # TODO for now just check that is an instance of Script
            if isinstance(script, Script):
                self.hash160 = self._script_to_hash160(script)
            else:
                raise TypeError("A Script class is required.")
        else:
            raise TypeError("A valid address or hash160 is required.")

    @classmethod
    def from_address(cls, address: str) -> 'Address':
        """Creates an address object from an address string"""

        return cls(address=address)

    @classmethod
    def from_hash160(cls, hash160: str) -> 'Address':
        """Creates an address object from a hash160 string"""

        return cls(hash160=hash160)

    @classmethod
    def from_script(cls, script: Script) -> 'Address':
        """Creates an address object from a Script object"""

        return cls(script=script)

    def _address_to_hash160(self, address: str) -> str:
        """Converts an address to it's hash160 equivalent

        Base58CheckDecode the address and remove network_prefix and checksum.
        """

        addr_encoded = address.encode("utf-8")
        data_checksum = b58decode(addr_encoded)
        # network_prefix = data_checksum[:1]
        data = data_checksum[1:-4]
        # checksum = data_checksum[-4:]
        return b_to_h(data)

    def _script_to_hash160(self, script: Script) -> str:
        """Converts a script to it's hash160 equivalent

        RIPEMD160( SHA256( script ) ) - required for P2SH addresses
        """

        script_bytes = script.to_bytes()
        hashsha256 = hashlib.sha256(script_bytes).digest()
        hash160 = ripemd160(hashsha256)
        return b_to_h(hash160)

    def _is_hash160_valid(self, hash160: str) -> bool:
        """Checks is a hash160 hex string is valid"""

        # check the size -- should be 20 bytes, 40 characters in hexadecimal string
        if len(hash160) != 40:
            return False

        # check all (string) digits are hex
        try:
            int(hash160, 16)
            return True
        except ValueError:
            return False

    def _is_address_valid(self, address: str) -> bool:
        """Checks is an address string is valid"""

        digits_58_pattern = (
            r"[^123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]"
        )

        # check for invalid characters
        if re.search(digits_58_pattern, address):
            return False

        # check for length (26-35 characters)
        # TODO: need to confirm the possible length!
        if len(address) < 26 or len(address) > 35:
            return False

        # get data, network_prefix and checksum
        data_checksum = b58decode(address.encode("utf-8"))
        data = data_checksum[:-4]
        network_prefix = data_checksum[:1]
        checksum = data_checksum[-4:]

        # check correct network (depending on address type)
        if self.get_type() == P2PKH_ADDRESS:
            if network_prefix != NETWORK_P2PKH_PREFIXES[get_network()]:
                return False
        elif self.get_type() == P2SH_ADDRESS:
            if network_prefix != NETWORK_P2SH_PREFIXES[get_network()]:
                return False

        # check address' checksum
        data_hash = hashlib.sha256(hashlib.sha256(data).digest()).digest()

        if data_hash[0:4] != checksum:
            return False

        return True

    def to_hash160(self) -> str:
        """Returns as hash160 hex string"""

        return self.hash160

    def get_type(self) -> str:
        """Returns the type of address"""
        return ""

    def to_string(self) -> str:
        """Returns as address string

        |  Pseudocode:
        |      network_prefix = (1 byte version number)
        |      data = network_prefix + hash160_bytes
        |      data_hash = SHA-256( SHA-256( hash160_bytes ) )
        |      checksum = (first 4 bytes of data_hash)
        |      address_bytes = Base58CheckEncode( data + checksum )
        """
        hash160_bytes = h_to_b(self.hash160)

        data = b""
        if self.get_type() == P2PKH_ADDRESS:
            data = NETWORK_P2PKH_PREFIXES[get_network()] + hash160_bytes
        elif self.get_type() == P2SH_ADDRESS:
            data = NETWORK_P2SH_PREFIXES[get_network()] + hash160_bytes

        data_hash = hashlib.sha256(hashlib.sha256(data).digest()).digest()
        checksum = data_hash[0:4]
        address_bytes = b58encode(data + checksum)

        return address_bytes.decode("utf-8")

    def to_script_pub_key(self) -> Script:
        """Overriden from subclasses"""
        return Script([])


class P2pkhAddress(Address):
    """Encapsulates a P2PKH address.

    Check Address class for details

    Methods
    -------
    to_script_pub_key()
        returns the scriptPubKey (P2PKH) that corresponds to this address
    get_type()
        returns the type of address
    """

    def __init__(
        self, address: Optional[str] = None, hash160: Optional[str] = None
    ) -> None:
        super().__init__(address=address, hash160=hash160)

    def to_script_pub_key(self) -> Script:
        """Returns the scriptPubKey (P2PKH) that corresponds to this address"""
        return Script(
            ["OP_DUP", "OP_HASH160", self.to_hash160(), "OP_EQUALVERIFY", "OP_CHECKSIG"]
        )

    def get_type(self) -> str:
        """Returns the type of address"""
        return P2PKH_ADDRESS


class P2shAddress(Address):
    """Encapsulates a P2SH address.

    Check Address class for details

    Methods
    -------
    to_script_pub_key()
        returns the scriptPubKey (P2SH) that corresponds to this address
    get_type()
        returns the type of address
    """

    def __init__(
        self,
        address: Optional[str] = None,
        hash160: Optional[str] = None,
        script: Optional[Script] = None,
    ) -> None:
        super().__init__(address=address, hash160=hash160, script=script)

    def to_script_pub_key(self) -> Script:
        """Returns the scriptPubKey (P2SH) that corresponds to this address"""
        return Script(["OP_HASH160", self.to_hash160(), "OP_EQUAL"])

    def get_type(self) -> str:
        """Returns the type of address"""
        return P2SH_ADDRESS


class SegwitAddress(ABC):
    """Represents a Bitcoin segwit address

    Note that currently the python bech32[m] reference implementation is used (by
    Pieter Wuille).

    Attributes
    ----------
    witness_program : str
        for segwit v0 this is the hash string representation of either the address;
        it can be either a public key hash (P2WPKH) or the hash of the script (P2WSH)

        for segwit v1 (aka taproot) this is the public key

    Methods
    -------
    from_address(address)
        instantiates an object from address string encoding
    from_program(hash_str)
        instantiates an object from a witness program hex string
    from_script(witness_script)
        instantiates an object from a witness_script
    to_string()
        returns the address's string encoding (Bech32)
    to_hash()
        returns the address's hash hex string representation

    Raises
    ------
    TypeError
        No parameters passed
    ValueError
        If an invalid address or hash is provided.
    """

    @abstractmethod
    def __init__(
        self,
        address: Optional[str] = None,
        witness_program: Optional[str] = None,
        script: Optional[Script] = None,
        version: str = P2WPKH_ADDRESS_V0,
    ) -> None:
        """
        Parameters
        ----------
        address : str
            the address as a string
        witness_program : str
            the witness program hex string representation
        script : Script object
            instantiates an Address object from a witness script
        version : str
            specifies the default segwit version

        Raises
        ------
        TypeError
            No parameters passed
        ValueError
            If an invalid address or hash is provided.
        """

        self.version = version
        if self.version == P2WPKH_ADDRESS_V0 or self.version == P2WSH_ADDRESS_V0:
            self.segwit_num_version = 0
        elif self.version == P2TR_ADDRESS_V1:
            self.segwit_num_version = 1
        else:
            raise TypeError("A valid segwit version is required.")

        # witness_program covers both v0 and v1
        if witness_program:
            self.witness_program = witness_program
        elif address:
            self.witness_program = self._address_to_hash(address)
        elif script:
            # TODO for now just check that is an instance of Script
            if isinstance(script, Script):
                self.witness_program = self._script_to_hash(script)
            else:
                raise TypeError("A Script class is required.")
        else:
            raise TypeError("A valid address or witness program is required.")

    @classmethod
    def from_address(cls, address: str) -> 'SegwitAddress':
        """Creates an address object from an address string"""

        return cls(address=address)

    @classmethod
    def from_witness_program(cls, witness_program: str) -> 'SegwitAddress':
        """Creates an address object from a hash string"""

        return cls(witness_program=witness_program)

    @classmethod
    def from_script(cls, script: Script) -> 'SegwitAddress':
        """Creates an address object from a Script object"""

        return cls(script=script)

    def _address_to_hash(self, address: str) -> str:
        """Converts an address to it's hash equivalent

        The size of the address determines between P2WPKH and P2WSH.
        Then Bech32 decodes the address removing network prefix, checksum,
        witness version.

        Uses a segwit's python reference implementation for now. (TODO)
        """

        witness_version, witness_int_array = bitcoinutils.bech32.decode(  # type: ignore
            NETWORK_SEGWIT_PREFIXES[get_network()], address
        )
        if witness_version is None:
            raise ValueError("Invalid value for parameter address.")
        if witness_version != self.segwit_num_version:
            raise TypeError("Invalid segwit version.")

        assert witness_int_array is not None
        return b_to_h(bytes(witness_int_array))

    def _script_to_hash(self, script: Script) -> str:
        """Converts a script to it's hash equivalent"""

        script_bytes = script.to_bytes()
        hashsha256 = hashlib.sha256(script_bytes).digest()
        return b_to_h(hashsha256)

    def to_witness_program(self) -> str:
        """Returns witness program as hex string"""

        return self.witness_program

    def to_string(self) -> str:
        """Returns as address string

        Uses a segwit's python reference implementation for now. (TODO)
        """

        hash_bytes = h_to_b(self.witness_program)
        witness_int_array = memoryview(hash_bytes).tolist()

        return bitcoinutils.bech32.encode(  # type: ignore
            NETWORK_SEGWIT_PREFIXES[get_network()],
            self.segwit_num_version,
            witness_int_array,
        )

    def to_script_pub_key(self) -> Script:
        """Overriden from subclasses"""
        return Script([])


class P2wpkhAddress(SegwitAddress):
    """Encapsulates a P2WPKH address.

    Check Address class for details

    Methods
    -------
    to_script_pub_key()
        returns the scriptPubKey of a P2WPKH witness script
    get_type()
        returns the type of address
    """

    # TODO allow creation directly from Bech32 address !!
    def __init__(
        self,
        address: Optional[str] = None,
        witness_program: Optional[str] = None,  # script=None, ?
        version: str = P2WPKH_ADDRESS_V0,
    ) -> None:
        """Allow creation only from hash160 of public key"""

        super().__init__(
            address=address,
            witness_program=witness_program,  # script=None, ?
            version=P2WPKH_ADDRESS_V0,
        )  # non-variable version

    def to_script_pub_key(self) -> Script:
        """Returns the scriptPubKey of a P2WPKH witness script"""
        return Script(["OP_0", self.to_witness_program()])

    def get_type(self) -> str:
        """Returns the type of address"""
        return self.version


class P2wshAddress(SegwitAddress):
    """Encapsulates a P2WSH address.

    Check Address class for details

    Methods
    -------
    from_script(witness_script)
        instantiates an object from a witness_script
    get_type()
        returns the type of address
    """

    def __init__(
        self,
        address: Optional[str] = None,
        witness_program: Optional[str] = None,
        script: Optional[Script] = None,
        version: str = P2WSH_ADDRESS_V0,
    ) -> None:
        """Allow creation only from hash160 of public key"""

        super().__init__(
            address=None, witness_program=None, script=script, version=P2WSH_ADDRESS_V0
        )  # non-variable version

    def to_script_pub_key(self) -> Script:
        """Returns the scriptPubKey of a P2WPKH witness script"""
        return Script(["OP_0", self.to_witness_program()])

    def get_type(self) -> str:
        """Returns the type of address"""
        return self.version


class P2trAddress(SegwitAddress):
    """Encapsulates a P2TR (Taproot) address.

    Check Address class for details

    Methods
    -------
    to_script_pub_key()
        returns the scriptPubKey of a P2TR witness script
    get_type()
        returns the type of address
    """

    def __init__(
        self,
        address: Optional[str] = None,
        witness_program: Optional[str] = None,  # script=None, ?
        version: str = P2TR_ADDRESS_V1,
        is_odd: bool = False,
    ) -> None:
        """Allow creation only from witness program"""

        self.odd = is_odd

        super().__init__(
            address=address,
            witness_program=witness_program,  # script=None, ?
            version=P2TR_ADDRESS_V1,
        )

    def to_script_pub_key(self) -> Script:
        """Returns the scriptPubKey of a P2TR witness script"""
        return Script(["OP_1", self.to_witness_program()])

    def get_type(self) -> str:
        """Returns the type of address"""
        return self.version

    def is_odd(self) -> bool:
        """Returns True if the y coordinate of the public key is odd and
        False otherwise."""

        return self.odd


def main():
    pass


if __name__ == "__main__":
    main()
