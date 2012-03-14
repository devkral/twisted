# -*- test-case-name: twisted.test.test_sip -*-
# Copyright (c) Twisted Matrix Laboratories.
# See LICENSE for details.


"""Session Initialization Protocol tests."""

from twisted.trial import unittest, util
from twisted.protocols import sip
from twisted.internet import defer, reactor, utils
from twisted.python.versions import Version

from twisted.test import proto_helpers

from twisted import cred
import twisted.cred.portal
import twisted.cred.checkers

from zope.interface import implements


# request, prefixed by random CRLFs
request1 = "\n\r\n\n\r" + """\
INVITE sip:foo SIP/2.0
From: mo
To: joe
Content-Length: 4

abcd""".replace("\n", "\r\n")


# request, no content-length
request2 = """INVITE sip:foo SIP/2.0
From: mo
To: joe

1234""".replace("\n", "\r\n")


# request, with garbage after
request3 = """INVITE sip:foo SIP/2.0
From: mo
To: joe
Content-Length: 4

1234

lalalal""".replace("\n", "\r\n")


# three requests
request4 = """INVITE sip:foo SIP/2.0
From: mo
To: joe
Content-Length: 0

INVITE sip:loop SIP/2.0
From: foo
To: bar
Content-Length: 4

abcdINVITE sip:loop SIP/2.0
From: foo
To: bar
Content-Length: 4

1234""".replace("\n", "\r\n")


# response, no content
response1 = """SIP/2.0 200 OK
From:  foo
To:bar
Content-Length: 0

""".replace("\n", "\r\n")


# short header version
request_short = """\
INVITE sip:foo SIP/2.0
f: mo
t: joe
l: 4

abcd""".replace("\n", "\r\n")


request_natted = """\
INVITE sip:foo SIP/2.0
Via: SIP/2.0/UDP 10.0.0.1:5060;rport

""".replace("\n", "\r\n")



class TestRealm:
    def requestAvatar(self, avatarId, mind, *interfaces):
        return sip.IContact, None, lambda: None



class TestHeaderCapitalize(unittest.TestCase):

    def test_simpleHeaderCapitalized(self):
        r = sip.Request("INVITE", "sip:foo")
        r.addHeader("foo", "bar")
        self.assertEqual(
            r.toString(),
            "INVITE sip:foo SIP/2.0\r\nFoo: bar\r\n\r\n")


    def test_complexHeaderCapitalized(self):
        r = sip.Request("INVITE", "sip:foo")
        r.addHeader("foo-bar-baz", "quux")
        self.assertEqual(
            r.toString(),
            "INVITE sip:foo SIP/2.0\r\nFoo-Bar-Baz: quux\r\n\r\n")


    def test_specialCaseHeaderCapitalized(self):
        r = sip.Request("INVITE", "sip:foo")
        r.addHeader("www-authenticate", "foo")
        self.assertEqual(
            r.toString(),
            "INVITE sip:foo SIP/2.0\r\nWWW-Authenticate: foo\r\n\r\n")




class MessageParsingTestCase(unittest.TestCase):
    def setUp(self):
        self.l = []
        self.parser = sip.MessagesParser(self.l.append)

    def feedMessage(self, message):
        self.parser.dataReceived(message)
        self.parser.dataDone()

    def validateMessage(self, m, method, uri, headers, body):
        """Validate Requests."""
        self.assertEqual(m.method, method)
        self.assertEqual(m.uri.toString(), uri)
        self.assertEqual(m.headers, headers)
        self.assertEqual(m.body, body)
        self.assertEqual(m.finished, 1)

    def testSimple(self):
        l = self.l
        self.feedMessage(request1)
        self.assertEqual(len(l), 1)
        self.validateMessage(
            l[0], "INVITE", "sip:foo",
            {"from": ["mo"], "to": ["joe"], "content-length": ["4"]},
            "abcd")

    def testTwoMessages(self):
        l = self.l
        self.feedMessage(request1)
        self.feedMessage(request2)
        self.assertEqual(len(l), 2)
        self.validateMessage(
            l[0], "INVITE", "sip:foo",
            {"from": ["mo"], "to": ["joe"], "content-length": ["4"]},
            "abcd")
        self.validateMessage(l[1], "INVITE", "sip:foo",
                             {"from": ["mo"], "to": ["joe"]},
                             "1234")

    def testGarbage(self):
        l = self.l
        self.feedMessage(request3)
        self.assertEqual(len(l), 1)
        self.validateMessage(
            l[0], "INVITE", "sip:foo",
            {"from": ["mo"], "to": ["joe"], "content-length": ["4"]},
            "1234")

    def testThreeInOne(self):
        l = self.l
        self.feedMessage(request4)
        self.assertEqual(len(l), 3)
        self.validateMessage(
            l[0], "INVITE", "sip:foo",
            {"from": ["mo"], "to": ["joe"], "content-length": ["0"]},
            "")
        self.validateMessage(
            l[1], "INVITE", "sip:loop",
            {"from": ["foo"], "to": ["bar"], "content-length": ["4"]},
            "abcd")
        self.validateMessage(
            l[2], "INVITE", "sip:loop",
            {"from": ["foo"], "to": ["bar"], "content-length": ["4"]},
            "1234")

    def testShort(self):
        l = self.l
        self.feedMessage(request_short)
        self.assertEqual(len(l), 1)
        self.validateMessage(
            l[0], "INVITE", "sip:foo",
            {"from": ["mo"], "to": ["joe"], "content-length": ["4"]},
            "abcd")

    def testSimpleResponse(self):
        l = self.l
        self.feedMessage(response1)
        self.assertEqual(len(l), 1)
        m = l[0]
        self.assertEqual(m.code, 200)
        self.assertEqual(m.phrase, "OK")
        self.assertEqual(
            m.headers,
            {"from": ["foo"], "to": ["bar"], "content-length": ["0"]})
        self.assertEqual(m.body, "")
        self.assertEqual(m.finished, 1)


class MessageParsingTestCase2(MessageParsingTestCase):
    """Same as base class, but feed data char by char."""

    def feedMessage(self, message):
        for c in message:
            self.parser.dataReceived(c)
        self.parser.dataDone()


class MakeMessageTestCase(unittest.TestCase):

    def testRequest(self):
        r = sip.Request("INVITE", "sip:foo")
        r.addHeader("foo", "bar")
        self.assertEqual(
            r.toString(),
            "INVITE sip:foo SIP/2.0\r\nFoo: bar\r\n\r\n")

    def testResponse(self):
        r = sip.Response(200, "OK")
        r.addHeader("foo", "bar")
        r.addHeader("Content-Length", "4")
        r.bodyDataReceived("1234")
        self.assertEqual(
            r.toString(),
            "SIP/2.0 200 OK\r\nFoo: bar\r\nContent-Length: 4\r\n\r\n1234")

    def testStatusCode(self):
        r = sip.Response(200)
        self.assertEqual(r.toString(), "SIP/2.0 200 OK\r\n\r\n")


class ViaTestCase(unittest.TestCase):

    def checkRoundtrip(self, v):
        s = v.toString()
        self.assertEqual(s, sip.parseViaHeader(s).toString())

    def testExtraWhitespace(self):
        v1 = sip.parseViaHeader('SIP/2.0/UDP 192.168.1.1:5060')
        v2 = sip.parseViaHeader('SIP/2.0/UDP     192.168.1.1:5060')
        self.assertEqual(v1.transport, v2.transport)
        self.assertEqual(v1.host, v2.host)
        self.assertEqual(v1.port, v2.port)

    def test_complex(self):
        """
        Test parsing a Via header with one of everything.
        """
        s = ("SIP/2.0/UDP first.example.com:4000;ttl=16;maddr=224.2.0.1"
             " ;branch=a7c6a8dlze (Example)")
        v = sip.parseViaHeader(s)
        self.assertEqual(v.transport, "UDP")
        self.assertEqual(v.host, "first.example.com")
        self.assertEqual(v.port, 4000)
        self.assertEqual(v.rport, None)
        self.assertEqual(v.rportValue, None)
        self.assertEqual(v.rportRequested, False)
        self.assertEqual(v.ttl, 16)
        self.assertEqual(v.maddr, "224.2.0.1")
        self.assertEqual(v.branch, "a7c6a8dlze")
        self.assertEqual(v.hidden, 0)
        self.assertEqual(v.toString(),
                          "SIP/2.0/UDP first.example.com:4000"
                          ";ttl=16;branch=a7c6a8dlze;maddr=224.2.0.1")
        self.checkRoundtrip(v)

    def test_simple(self):
        """
        Test parsing a simple Via header.
        """
        s = "SIP/2.0/UDP example.com;hidden"
        v = sip.parseViaHeader(s)
        self.assertEqual(v.transport, "UDP")
        self.assertEqual(v.host, "example.com")
        self.assertEqual(v.port, 5060)
        self.assertEqual(v.rport, None)
        self.assertEqual(v.rportValue, None)
        self.assertEqual(v.rportRequested, False)
        self.assertEqual(v.ttl, None)
        self.assertEqual(v.maddr, None)
        self.assertEqual(v.branch, None)
        self.assertEqual(v.hidden, True)
        self.assertEqual(v.toString(),
                          "SIP/2.0/UDP example.com:5060;hidden")
        self.checkRoundtrip(v)

    def testSimpler(self):
        v = sip.Via("example.com")
        self.checkRoundtrip(v)


    def test_deprecatedRPort(self):
        """
        Setting rport to True is deprecated, but still produces a Via header
        with the expected properties.
        """
        v = sip.Via("foo.bar", rport=True)

        warnings = self.flushWarnings(
            offendingFunctions=[self.test_deprecatedRPort])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(
            warnings[0]['message'],
            'rport=True is deprecated since Twisted 9.0.')
        self.assertEqual(
            warnings[0]['category'],
            DeprecationWarning)

        self.assertEqual(v.toString(), "SIP/2.0/UDP foo.bar:5060;rport")
        self.assertEqual(v.rport, True)
        self.assertEqual(v.rportRequested, True)
        self.assertEqual(v.rportValue, None)


    def test_rport(self):
        """
        An rport setting of None should insert the parameter with no value.
        """
        v = sip.Via("foo.bar", rport=None)
        self.assertEqual(v.toString(), "SIP/2.0/UDP foo.bar:5060;rport")
        self.assertEqual(v.rportRequested, True)
        self.assertEqual(v.rportValue, None)


    def test_rportValue(self):
        """
        An rport numeric setting should insert the parameter with the number
        value given.
        """
        v = sip.Via("foo.bar", rport=1)
        self.assertEqual(v.toString(), "SIP/2.0/UDP foo.bar:5060;rport=1")
        self.assertEqual(v.rportRequested, False)
        self.assertEqual(v.rportValue, 1)
        self.assertEqual(v.rport, 1)


    def testNAT(self):
        s = "SIP/2.0/UDP 10.0.0.1:5060;received=22.13.1.5;rport=12345"
        v = sip.parseViaHeader(s)
        self.assertEqual(v.transport, "UDP")
        self.assertEqual(v.host, "10.0.0.1")
        self.assertEqual(v.port, 5060)
        self.assertEqual(v.received, "22.13.1.5")
        self.assertEqual(v.rport, 12345)

        self.assertNotEquals(v.toString().find("rport=12345"), -1)


    def test_unknownParams(self):
       """
       Parsing and serializing Via headers with unknown parameters should work.
       """
       s = "SIP/2.0/UDP example.com:5060;branch=a12345b;bogus;pie=delicious"
       v = sip.parseViaHeader(s)
       self.assertEqual(v.toString(), s)



class URITestCase(unittest.TestCase):
    """
    Tests for L{sip.URI} and {sip.parseURL}.
    """

    def testRoundtrip(self):
        for url in [
            "sip:j.doe@big.com",
            "sip:j.doe:secret@big.com;transport=tcp",
            "sip:j.doe@big.com?Subject=project",
            "sip:example.com",
            ]:
            self.assertEqual(sip.parseURL(url).toString(), url)


    def test_complex(self):
        """
        Test parsing and printing a URI with one of everything.
        """
        s = ("sip:user:pass@hosta:123;transport=udp;user=phone;method=foo;"
             "ttl=12;maddr=1.2.3.4;blah;goo=bar?foo-baz=b&c=d")
        url = sip.parseURL(s)
        for k, v in [("username", "user"), ("password", "pass"),
                     ("host", "hosta"), ("port", 123),
                     ("transport", "udp"), ("usertype", "phone"),
                     ("method", "foo"), ("ttl", 12),
                     ("maddr", "1.2.3.4"), ("other", {"blah": "",
                                                      "goo": "bar"}),
                     ("headers", {"foo-baz": "b", "c": "d"})]:
            self.assertEqual(getattr(url, k), v)
        self.assertEquals(
            str(url),
            'sip:user:pass@hosta:123;user=phone;transport=udp;'
            'ttl=12;maddr=1.2.3.4;method=foo;blah;goo=bar?C=d&Foo-Baz=b')


    def test_headers(self):
        """
        SIP headers included in the URI are parsed correctly.
        """

        uris = ["sip:foo@bar.com?header=value",
                "sip:foo@bar.com:5060?header=value",
                "sip:foo@bar.com;method=invite?header=value"]
        for uri in uris:
            self.assertEquals(sip.parseURL(uri).headers,
                              {"header": "value"})


    def test_invalidScheme(self):
        """
        Attempts to parse unsupported URI schemes are rejected.
        """
        self.assertRaises(sip.SIPError, sip.parseURL, "http://example.com/")
        self.assertRaises(sip.SIPError, sip.parseURL, "sips:bob@example.com")


    def test_hash(self):
        """
        URIs are hashable.
        """
        s1 = ("sip:user:pass@hosta:123;transport=udp;user=phone;method=foo;"
             "ttl=12;maddr=1.2.3.4;blah;goo=bar?foo-baz=b&c=d")
        s2 = ("sip:user:pass@hostb:123;transport=udp;user=phone;method=foo;"
             "ttl=12;maddr=1.2.3.4;blah;goo=bar?foo-baz=b&c=d")
        s3 = ("sip:user:pass@hosta:123;transport=udp;user=voip;method=foo;"
             "ttl=12;maddr=1.2.3.4;blah;goo=bar?foo-baz=b&c=d")
        s4 = ("sip:user:pass@hosta:123;transport=udp;user=phone;method=foo;"
             "ttl=16;maddr=1.2.3.4;blah;goo=bar?foo-baz=b&c=d")
        s5 = ("sip:user:pass@hosta:123;transport=udp;user=phone;method=foo;"
             "ttl=12;maddr=1.2.3.5;blah;goo=bar?foo-baz=b&c=d")
        s6 = ("sip:user:pass@hosta:123;transport=udp;user=phone;method=foo;"
             "ttl=12;maddr=1.2.3.4;blah;foo=bar?foo-baz=b&c=d")
        s7 = ("sip:user:pass@hosta:123;transport=udp;user=phone;method=foo;"
             "ttl=12;maddr=1.2.3.4;blah;goo=bar?foo-baz=b&c=e")
        d = {
            sip.URI("example.com"): -2,
            sip.URI("example.com", "bob"): -1,
            }
        for i, s in enumerate([s1, s2, s3, s4, s5, s6, s7]):
            d[sip.parseURL(s)] = i
        self.assertEqual(d[sip.URI("example.com")], -2)
        self.assertEqual(d[sip.URI("example.com", "bob")], -1)
        for i, s in enumerate([s1, s2, s3, s4, s5, s6, s7]):
            self.assertEqual(d[sip.parseURL(s)], i)


    def test_escaping(self):
        """
        Percent-encoded characters are decoded and encoded correctly.
        """
        uriString = ("sip:sips%3Auser%40example.com:x%20x@example.net"
                           ";m%65thod=foo%00baz?a%62c-foo=de%66")
        uri = sip.parseURL(uriString)
        self.assertEqual(uri.username, "sips:user@example.com")
        self.assertEqual(uri.password, "x x")
        self.assertEqual(uri.method, "foo\x00baz")
        self.assertEqual(uri.headers, {"abc-foo": "def"})
        self.assertEqual(uri.toString(),
                         ("sip:sips%3Auser%40example.com:x%20x@example.net"
                           ";method=foo%00baz?Abc-Foo=def"))


    def test_equivalence(self):
        """
        All the URIs the RFC says are equivalent should compare equal.
        """
        def assertEquivalentURIs(l, r):
            self.assertEqual(sip.parseURL(l), sip.parseURL(r))

        assertEquivalentURIs("sip:%61lice@atlanta.com;transport=TCP",
                             "sip:alice@AtLanTa.CoM;Transport=tcp")
        assertEquivalentURIs("sip:carol@chicago.com",
                             "sip:carol@chicago.com;newparam=5")
        assertEquivalentURIs("sip:carol@chicago.com",
                             "sip:carol@chicago.com;security=on")
        assertEquivalentURIs("sip:carol@chicago.com;security=on",
                             "sip:carol@chicago.com;newparam=5")
        assertEquivalentURIs("sip:biloxi.com;transport=tcp;method=REGISTER?"
                             "to=sip:bob%40biloxi.com",
                             "sip:biloxi.com;method=REGISTER;transport=tcp?"
                             "to=sip:bob%40biloxi.com")
        assertEquivalentURIs("sip:alice@atlanta.com?subject=project%20x"
                             "&priority=urgent",
                             "sip:alice@atlanta.com?priority=urgent&"
                             "subject=project%20x")


    def test_nonequivalence(self):
        """
        Ensure that certain difference between similar URIs prevent them from
        comparing equal.
        """
        def assertNonequivalent(l, r):
            self.assertNotEqual(sip.parseURL(l), sip.parseURL(r))

        assertNonequivalent("sip:carol@chicago.com;security=off",
                            "sip:carol@chicago.com;security=on")
        assertNonequivalent("SIP:ALICE@AtLanTa.CoM;Transport=udp",
                            "sip:alice@AtLanTa.CoM;Transport=UDP")
        assertNonequivalent("sip:bob@biloxi.com", "sip:bob@biloxi.com:5060")
        assertNonequivalent("sip:bob@biloxi.com",
                            "sip:bob@biloxi.com;transport=udp")
        assertNonequivalent("sip:bob@biloxi.com",
                            "sip:bob@biloxi.com:5060;transport=udp")
        assertNonequivalent("sip:bob@biloxi.com",
                            "sip:bob@biloxi.com:5060;transport=tcp")
        assertNonequivalent("sip:carol@chicago.com",
                            "sip:carol@chicago.com?Subject=next%20meeting")
        assertNonequivalent("sip:bob@localhost", "sip:bob@127.0.0.1")

    
    def test_capitalization(self):
        """
        Ensure that parameters and headers are correctly treated as case-
        insensitive (i.e. lowercase)
        """
        s1 = ("sip:user:pass@hosta:123;transport=udp;user=phone;method=foo;"
             "ttl=12;maddr=1.2.3.4;blah;goo=bar?foo-baz=b&c=e")
        s2 = ("sip:user:pass@hosta:123;transport=udp;user=phone;method=foo;"
             "ttl=12;maddr=1.2.3.4;blah;Goo=bar?foo-baz=b&c=e")        
        s3 = ("SIP:user:pass@hosta:123;transport=udp;user=phone;method=foo;"
             "ttl=12;maddr=1.2.3.4;blah;goo=bar?fOo-baz=b&c=e")
        self.assertEqual(sip.parseURL(s1), sip.parseURL(s2))
        self.assertEqual(sip.parseURL(s2), sip.parseURL(s3))



class ParseTestCase(unittest.TestCase):

    def testParseAddress(self):
        """
        Confirm that various names and addresses are parsed correctly.
        """
        for address, name, urls, params in [
            ('"A. G. Bell" <sip:foo@example.com>',
             "A. G. Bell", "sip:foo@example.com", {}),
            ("Anon <sip:foo@example.com>", "Anon", "sip:foo@example.com", {}),
            ('"A. G. Bell" <sip:foo@example.com>',
             "A. G. Bell", "sip:foo@example.com", {}),
            (' "A. G. Bell" <sip:foo@example.com>',
             "A. G. Bell", "sip:foo@example.com", {}),
            ('"Bell, A. G." <sip:bell@example.com>',
             "Bell, A. G.", "sip:bell@example.com", {}),
            ('" \\\\A. G. \\"Bell" <sip:foo@example.com>',
             " \\A. G. \"Bell", "sip:foo@example.com", {}),
            ('"\\x21A. G. Bell" <sip:foo@example.com>',
             "x21A. G. Bell", "sip:foo@example.com", {}),
            ("abcd1234-.!%*_+`'~ <sip:foo@example.com>",
             "abcd1234-.!%*_+`'~", "sip:foo@example.com", {}),
            ('"C\xc3\xa9sar" <sip:C%C3%A9sar@example.com>',
             u'C\xe9sar', 'sip:C%C3%A9sar@example.com', {}),
            ("Anon <sip:foo@example.com>",
             "Anon", "sip:foo@example.com", {}),
            ("sip:foo@example.com", "", "sip:foo@example.com", {}),
            ("<sip:foo@example.com>", "", "sip:foo@example.com", {}),
            ("foo <sip:foo@example.com>;tag=bar;foo=baz;boz",
             "foo", "sip:foo@example.com", {"tag": "bar", "foo": "baz",
                                            "boz": ""}),
            ("sip:foo@example.com;tag=bar;foo=baz",
             "", "sip:foo@example.com", {"tag": "bar", "foo": "baz"}),
            # test the use of name.decode('utf8', 'replace')
            ('"Invalid \xc3\x28" <sip:foo@example.com>',
             u"Invalid \ufffd(", "sip:foo@example.com", {}),
            ]:
            gname, gurl, gparams = sip.parseAddress(address)
            self.assertEqual(name, gname)
            self.assertEqual(gurl.toString(), urls)
            self.assertEqual(gparams, params)



class DummyLocator:
    implements(sip.ILocator)
    def getAddress(self, logicalURL):
        return defer.succeed(sip.URL("server.com", port=5060))



class FailingLocator:
    implements(sip.ILocator)
    def getAddress(self, logicalURL):
        return defer.fail(LookupError())



class ProxyTestCase(unittest.TestCase):

    def setUp(self):
        self.proxy = sip.Proxy("127.0.0.1")
        self.proxy.locator = DummyLocator()
        self.sent = []
        self.proxy.sendMessage = lambda dest, msg: self.sent.append((dest, msg))

    def testRequestForward(self):
        r = sip.Request("INVITE", "sip:foo")
        r.addHeader("via", sip.Via("1.2.3.4").toString())
        r.addHeader("via", sip.Via("1.2.3.5").toString())
        r.addHeader("foo", "bar")
        r.addHeader("to", "<sip:joe@server.com>")
        r.addHeader("contact", "<sip:joe@1.2.3.5>")
        self.proxy.datagramReceived(r.toString(), ("1.2.3.4", 5060))
        self.assertEqual(len(self.sent), 1)
        dest, m = self.sent[0]
        self.assertEqual(dest.port, 5060)
        self.assertEqual(dest.host, "server.com")
        self.assertEqual(m.uri.toString(), "sip:foo")
        self.assertEqual(m.method, "INVITE")
        self.assertEqual(m.headers["via"],
                          ["SIP/2.0/UDP 127.0.0.1:5060",
                           "SIP/2.0/UDP 1.2.3.4:5060",
                           "SIP/2.0/UDP 1.2.3.5:5060"])


    def testReceivedRequestForward(self):
        r = sip.Request("INVITE", "sip:foo")
        r.addHeader("via", sip.Via("1.2.3.4").toString())
        r.addHeader("foo", "bar")
        r.addHeader("to", "<sip:joe@server.com>")
        r.addHeader("contact", "<sip:joe@1.2.3.4>")
        self.proxy.datagramReceived(r.toString(), ("1.1.1.1", 5060))
        dest, m = self.sent[0]
        self.assertEqual(m.headers["via"],
                          ["SIP/2.0/UDP 127.0.0.1:5060",
                           "SIP/2.0/UDP 1.2.3.4:5060;received=1.1.1.1"])


    def testResponseWrongVia(self):
        # first via must match proxy's address
        r = sip.Response(200)
        r.addHeader("via", sip.Via("foo.com").toString())
        self.proxy.datagramReceived(r.toString(), ("1.1.1.1", 5060))
        self.assertEqual(len(self.sent), 0)

    def testResponseForward(self):
        r = sip.Response(200)
        r.addHeader("via", sip.Via("127.0.0.1").toString())
        r.addHeader("via", sip.Via("client.com", port=1234).toString())
        self.proxy.datagramReceived(r.toString(), ("1.1.1.1", 5060))
        self.assertEqual(len(self.sent), 1)
        dest, m = self.sent[0]
        self.assertEqual((dest.host, dest.port), ("client.com", 1234))
        self.assertEqual(m.code, 200)
        self.assertEqual(m.headers["via"], ["SIP/2.0/UDP client.com:1234"])

    def testReceivedResponseForward(self):
        r = sip.Response(200)
        r.addHeader("via", sip.Via("127.0.0.1").toString())
        r.addHeader(
            "via",
            sip.Via("10.0.0.1", received="client.com").toString())
        self.proxy.datagramReceived(r.toString(), ("1.1.1.1", 5060))
        self.assertEqual(len(self.sent), 1)
        dest, m = self.sent[0]
        self.assertEqual((dest.host, dest.port), ("client.com", 5060))

    def testResponseToUs(self):
        r = sip.Response(200)
        r.addHeader("via", sip.Via("127.0.0.1").toString())
        l = []
        self.proxy.gotResponse = lambda *a: l.append(a)
        self.proxy.datagramReceived(r.toString(), ("1.1.1.1", 5060))
        self.assertEqual(len(l), 1)
        m, addr = l[0]
        self.assertEqual(len(m.headers.get("via", [])), 0)
        self.assertEqual(m.code, 200)

    def testLoop(self):
        r = sip.Request("INVITE", "sip:foo")
        r.addHeader("via", sip.Via("1.2.3.4").toString())
        r.addHeader("via", sip.Via("127.0.0.1").toString())
        self.proxy.datagramReceived(r.toString(), ("client.com", 5060))
        self.assertEqual(self.sent, [])

    def testCantForwardRequest(self):
        r = sip.Request("INVITE", "sip:foo")
        r.addHeader("via", sip.Via("1.2.3.4").toString())
        r.addHeader("to", "<sip:joe@server.com>")
        self.proxy.locator = FailingLocator()
        self.proxy.datagramReceived(r.toString(), ("1.2.3.4", 5060))
        self.assertEqual(len(self.sent), 1)
        dest, m = self.sent[0]
        self.assertEqual((dest.host, dest.port), ("1.2.3.4", 5060))
        self.assertEqual(m.code, 404)
        self.assertEqual(m.headers["via"], ["SIP/2.0/UDP 1.2.3.4:5060"])

    def testCantForwardResponse(self):
        pass

    #testCantForwardResponse.skip = "not implemented yet"


class RegistrationTestCase(unittest.TestCase):

    def setUp(self):
        self.proxy = sip.RegisterProxy(host="127.0.0.1")
        self.registry = sip.InMemoryRegistry("bell.example.com")
        self.proxy.registry = self.proxy.locator = self.registry
        self.sent = []
        self.proxy.sendMessage = lambda dest, msg: self.sent.append((dest, msg))
    setUp = utils.suppressWarnings(setUp,
        util.suppress(category=DeprecationWarning,
            message=r'twisted.protocols.sip.DigestAuthorizer was deprecated'))

    def tearDown(self):
        for d, uri in self.registry.users.values():
            d.cancel()
        del self.proxy

    def register(self):
        r = sip.Request("REGISTER", "sip:bell.example.com")
        r.addHeader("to", "sip:joe@bell.example.com")
        r.addHeader("contact", "sip:joe@client.com:1234")
        r.addHeader("via", sip.Via("client.com").toString())
        self.proxy.datagramReceived(r.toString(), ("client.com", 5060))

    def unregister(self):
        r = sip.Request("REGISTER", "sip:bell.example.com")
        r.addHeader("to", "sip:joe@bell.example.com")
        r.addHeader("contact", "*")
        r.addHeader("via", sip.Via("client.com").toString())
        r.addHeader("expires", "0")
        self.proxy.datagramReceived(r.toString(), ("client.com", 5060))

    def testRegister(self):
        self.register()
        dest, m = self.sent[0]
        self.assertEqual((dest.host, dest.port), ("client.com", 5060))
        self.assertEqual(m.code, 200)
        self.assertEqual(m.headers["via"], ["SIP/2.0/UDP client.com:5060"])
        self.assertEqual(m.headers["to"], ["sip:joe@bell.example.com"])
        self.assertEqual(m.headers["contact"], ["sip:joe@client.com:5060"])
        self.failUnless(
            int(m.headers["expires"][0]) in (3600, 3601, 3599, 3598))
        self.assertEqual(len(self.registry.users), 1)
        dc, uri = self.registry.users["joe"]
        self.assertEqual(uri.toString(), "sip:joe@client.com:5060")
        d = self.proxy.locator.getAddress(sip.URL(username="joe",
                                                  host="bell.example.com"))
        d.addCallback(lambda desturl : (desturl.host, desturl.port))
        d.addCallback(self.assertEqual, ('client.com', 5060))
        return d

    def testUnregister(self):
        self.register()
        self.unregister()
        dest, m = self.sent[1]
        self.assertEqual((dest.host, dest.port), ("client.com", 5060))
        self.assertEqual(m.code, 200)
        self.assertEqual(m.headers["via"], ["SIP/2.0/UDP client.com:5060"])
        self.assertEqual(m.headers["to"], ["sip:joe@bell.example.com"])
        self.assertEqual(m.headers["contact"], ["sip:joe@client.com:5060"])
        self.assertEqual(m.headers["expires"], ["0"])
        self.assertEqual(self.registry.users, {})


    def addPortal(self):
        r = TestRealm()
        p = cred.portal.Portal(r)
        c = cred.checkers.InMemoryUsernamePasswordDatabaseDontUse()
        c.addUser('userXname@127.0.0.1', 'passXword')
        p.registerChecker(c)
        self.proxy.portal = p

    def testFailedAuthentication(self):
        self.addPortal()
        self.register()

        self.assertEqual(len(self.registry.users), 0)
        self.assertEqual(len(self.sent), 1)
        dest, m = self.sent[0]
        self.assertEqual(m.code, 401)


    def test_basicAuthentication(self):
        """
        Test that registration with basic authentication suceeds.
        """
        self.addPortal()
        self.proxy.authorizers = self.proxy.authorizers.copy()
        self.proxy.authorizers['basic'] = sip.BasicAuthorizer()
        warnings = self.flushWarnings(
            offendingFunctions=[self.test_basicAuthentication])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(
            warnings[0]['message'],
            "twisted.protocols.sip.BasicAuthorizer was deprecated in "
            "Twisted 9.0.0")
        self.assertEqual(
            warnings[0]['category'],
            DeprecationWarning)
        r = sip.Request("REGISTER", "sip:bell.example.com")
        r.addHeader("to", "sip:joe@bell.example.com")
        r.addHeader("contact", "sip:joe@client.com:1234")
        r.addHeader("via", sip.Via("client.com").toString())
        r.addHeader("authorization",
                    "Basic " + "userXname:passXword".encode('base64'))
        self.proxy.datagramReceived(r.toString(), ("client.com", 5060))

        self.assertEqual(len(self.registry.users), 1)
        self.assertEqual(len(self.sent), 1)
        dest, m = self.sent[0]
        self.assertEqual(m.code, 200)


    def test_failedBasicAuthentication(self):
        """
        Failed registration with basic authentication results in an
        unauthorized error response.
        """
        self.addPortal()
        self.proxy.authorizers = self.proxy.authorizers.copy()
        self.proxy.authorizers['basic'] = sip.BasicAuthorizer()
        warnings = self.flushWarnings(
            offendingFunctions=[self.test_failedBasicAuthentication])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(
            warnings[0]['message'],
            "twisted.protocols.sip.BasicAuthorizer was deprecated in "
            "Twisted 9.0.0")
        self.assertEqual(
            warnings[0]['category'],
            DeprecationWarning)
        r = sip.Request("REGISTER", "sip:bell.example.com")
        r.addHeader("to", "sip:joe@bell.example.com")
        r.addHeader("contact", "sip:joe@client.com:1234")
        r.addHeader("via", sip.Via("client.com").toString())
        r.addHeader(
            "authorization", "Basic " + "userXname:password".encode('base64'))
        self.proxy.datagramReceived(r.toString(), ("client.com", 5060))

        self.assertEqual(len(self.registry.users), 0)
        self.assertEqual(len(self.sent), 1)
        dest, m = self.sent[0]
        self.assertEqual(m.code, 401)


    def testWrongDomainRegister(self):
        r = sip.Request("REGISTER", "sip:wrong.com")
        r.addHeader("to", "sip:joe@bell.example.com")
        r.addHeader("contact", "sip:joe@client.com:1234")
        r.addHeader("via", sip.Via("client.com").toString())
        self.proxy.datagramReceived(r.toString(), ("client.com", 5060))
        self.assertEqual(len(self.sent), 0)

    def testWrongToDomainRegister(self):
        r = sip.Request("REGISTER", "sip:bell.example.com")
        r.addHeader("to", "sip:joe@foo.com")
        r.addHeader("contact", "sip:joe@client.com:1234")
        r.addHeader("via", sip.Via("client.com").toString())
        self.proxy.datagramReceived(r.toString(), ("client.com", 5060))
        self.assertEqual(len(self.sent), 0)

    def testWrongDomainLookup(self):
        self.register()
        url = sip.URL(username="joe", host="foo.com")
        d = self.proxy.locator.getAddress(url)
        self.assertFailure(d, LookupError)
        return d

    def testNoContactLookup(self):
        self.register()
        url = sip.URL(username="jane", host="bell.example.com")
        d = self.proxy.locator.getAddress(url)
        self.assertFailure(d, LookupError)
        return d


class Client(sip.Base):

    def __init__(self):
        sip.Base.__init__(self)
        self.received = []
        self.deferred = defer.Deferred()

    def handle_response(self, response, addr):
        self.received.append(response)
        self.deferred.callback(self.received)


class LiveTest(unittest.TestCase):

    def setUp(self):
        self.proxy = sip.RegisterProxy(host="127.0.0.1")
        self.registry = sip.InMemoryRegistry("bell.example.com")
        self.proxy.registry = self.proxy.locator = self.registry
        self.serverPort = reactor.listenUDP(
            0, self.proxy, interface="127.0.0.1")
        self.client = Client()
        self.clientPort = reactor.listenUDP(
            0, self.client, interface="127.0.0.1")
        self.serverAddress = (self.serverPort.getHost().host,
                              self.serverPort.getHost().port)
    setUp = utils.suppressWarnings(setUp,
        util.suppress(category=DeprecationWarning,
            message=r'twisted.protocols.sip.DigestAuthorizer was deprecated'))

    def tearDown(self):
        for d, uri in self.registry.users.values():
            d.cancel()
        d1 = defer.maybeDeferred(self.clientPort.stopListening)
        d2 = defer.maybeDeferred(self.serverPort.stopListening)
        return defer.gatherResults([d1, d2])

    def testRegister(self):
        p = self.clientPort.getHost().port
        r = sip.Request("REGISTER", "sip:bell.example.com")
        r.addHeader("to", "sip:joe@bell.example.com")
        r.addHeader("contact", "sip:joe@127.0.0.1:%d" % p)
        r.addHeader("via", sip.Via("127.0.0.1", port=p).toString())
        self.client.sendMessage(
            sip.URL(host="127.0.0.1", port=self.serverAddress[1]), r)
        d = self.client.deferred
        def check(received):
            self.assertEqual(len(received), 1)
            r = received[0]
            self.assertEqual(r.code, 200)
        d.addCallback(check)
        return d

    def test_amoralRPort(self):
        """
        rport is allowed without a value, apparently because server
        implementors might be too stupid to check the received port
        against 5060 and see if they're equal, and because client
        implementors might be too stupid to bind to port 5060, or set a
        value on the rport parameter they send if they bind to another
        port.
        """
        p = self.clientPort.getHost().port
        r = sip.Request("REGISTER", "sip:bell.example.com")
        r.addHeader("to", "sip:joe@bell.example.com")
        r.addHeader("contact", "sip:joe@127.0.0.1:%d" % p)
        r.addHeader("via", sip.Via("127.0.0.1", port=p, rport=True).toString())
        warnings = self.flushWarnings(
            offendingFunctions=[self.test_amoralRPort])
        self.assertEqual(len(warnings), 1)
        self.assertEqual(
            warnings[0]['message'],
            'rport=True is deprecated since Twisted 9.0.')
        self.assertEqual(
            warnings[0]['category'],
            DeprecationWarning)
        self.client.sendMessage(sip.URL(host="127.0.0.1",
                                        port=self.serverAddress[1]),
                                r)
        d = self.client.deferred
        def check(received):
            self.assertEqual(len(received), 1)
            r = received[0]
            self.assertEqual(r.code, 200)
        d.addCallback(check)
        return d



registerRequest = """
REGISTER sip:intarweb.us SIP/2.0\r
Via: SIP/2.0/UDP 192.168.1.100:50609\r
From: <sip:exarkun@intarweb.us:50609>\r
To: <sip:exarkun@intarweb.us:50609>\r
Contact: "exarkun" <sip:exarkun@192.168.1.100:50609>\r
Call-ID: 94E7E5DAF39111D791C6000393764646@intarweb.us\r
CSeq: 9898 REGISTER\r
Expires: 500\r
User-Agent: X-Lite build 1061\r
Content-Length: 0\r
\r
"""

challengeResponse = """\
SIP/2.0 401 Unauthorized\r
Via: SIP/2.0/UDP 192.168.1.100:50609;received=127.0.0.1;rport=5632\r
To: <sip:exarkun@intarweb.us:50609>\r
From: <sip:exarkun@intarweb.us:50609>\r
Call-ID: 94E7E5DAF39111D791C6000393764646@intarweb.us\r
CSeq: 9898 REGISTER\r
WWW-Authenticate: Digest nonce="92956076410767313901322208775",opaque="1674186428",qop-options="auth",algorithm="MD5",realm="intarweb.us"\r
\r
"""

authRequest = """\
REGISTER sip:intarweb.us SIP/2.0\r
Via: SIP/2.0/UDP 192.168.1.100:50609\r
From: <sip:exarkun@intarweb.us:50609>\r
To: <sip:exarkun@intarweb.us:50609>\r
Contact: "exarkun" <sip:exarkun@192.168.1.100:50609>\r
Call-ID: 94E7E5DAF39111D791C6000393764646@intarweb.us\r
CSeq: 9899 REGISTER\r
Expires: 500\r
Authorization: Digest username="exarkun",realm="intarweb.us",nonce="92956076410767313901322208775",response="4a47980eea31694f997369214292374b",uri="sip:intarweb.us",algorithm=MD5,opaque="1674186428"\r
User-Agent: X-Lite build 1061\r
Content-Length: 0\r
\r
"""

okResponse = """\
SIP/2.0 200 OK\r
Via: SIP/2.0/UDP 192.168.1.100:50609;received=127.0.0.1;rport=5632\r
To: <sip:exarkun@intarweb.us:50609>\r
From: <sip:exarkun@intarweb.us:50609>\r
Call-ID: 94E7E5DAF39111D791C6000393764646@intarweb.us\r
CSeq: 9899 REGISTER\r
Contact: sip:exarkun@127.0.0.1:5632\r
Expires: 3600\r
Content-Length: 0\r
\r
"""

class FakeDigestAuthorizer(sip.DigestAuthorizer):
    def generateNonce(self):
        return '92956076410767313901322208775'
    def generateOpaque(self):
        return '1674186428'


class FakeRegistry(sip.InMemoryRegistry):
    """Make sure expiration is always seen to be 3600.

    Otherwise slow reactors fail tests incorrectly.
    """

    def _cbReg(self, reg):
        if 3600 < reg.secondsToExpiry or reg.secondsToExpiry < 3598:
            raise RuntimeError(
                "bad seconds to expire: %s" % reg.secondsToExpiry)
        reg.secondsToExpiry = 3600
        return reg

    def getRegistrationInfo(self, uri):
        d = sip.InMemoryRegistry.getRegistrationInfo(self, uri)
        return d.addCallback(self._cbReg)

    def registerAddress(self, domainURL, logicalURL, physicalURL):
        d = sip.InMemoryRegistry.registerAddress(
            self, domainURL, logicalURL, physicalURL)
        return d.addCallback(self._cbReg)

class AuthorizationTestCase(unittest.TestCase):
    def setUp(self):
        self.proxy = sip.RegisterProxy(host="intarweb.us")
        self.proxy.authorizers = self.proxy.authorizers.copy()
        self.proxy.authorizers['digest'] = FakeDigestAuthorizer()

        self.registry = FakeRegistry("intarweb.us")
        self.proxy.registry = self.proxy.locator = self.registry
        self.transport = proto_helpers.FakeDatagramTransport()
        self.proxy.transport = self.transport

        r = TestRealm()
        p = cred.portal.Portal(r)
        c = cred.checkers.InMemoryUsernamePasswordDatabaseDontUse()
        c.addUser('exarkun@intarweb.us', 'password')
        p.registerChecker(c)
        self.proxy.portal = p
    setUp = utils.suppressWarnings(setUp,
        util.suppress(category=DeprecationWarning,
            message=r'twisted.protocols.sip.DigestAuthorizer was deprecated'))

    def tearDown(self):
        for d, uri in self.registry.users.values():
            d.cancel()
        del self.proxy

    def testChallenge(self):
        self.proxy.datagramReceived(registerRequest, ("127.0.0.1", 5632))

        self.assertEqual(
            self.transport.written[-1],
            ((challengeResponse, ("127.0.0.1", 5632)))
        )
        self.transport.written = []

        self.proxy.datagramReceived(authRequest, ("127.0.0.1", 5632))

        self.assertEqual(
            self.transport.written[-1],
            ((okResponse, ("127.0.0.1", 5632)))
        )
    testChallenge.suppress = [
        util.suppress(
            category=DeprecationWarning,
            message=r'twisted.protocols.sip.DigestAuthorizer was deprecated'),
        util.suppress(
            category=DeprecationWarning,
            message=r'twisted.protocols.sip.DigestedCredentials was deprecated'),
        util.suppress(
            category=DeprecationWarning,
            message=r'twisted.protocols.sip.DigestCalcHA1 was deprecated'),
        util.suppress(
            category=DeprecationWarning,
            message=r'twisted.protocols.sip.DigestCalcResponse was deprecated')]



class DeprecationTests(unittest.TestCase):
    """
    Tests for deprecation of obsolete components of L{twisted.protocols.sip}.
    """

    def test_deprecatedDigestCalcHA1(self):
        """
        L{sip.DigestCalcHA1} is deprecated.
        """
        self.callDeprecated(Version("Twisted", 9, 0, 0),
                            sip.DigestCalcHA1, '', '', '', '', '', '')


    def test_deprecatedDigestCalcResponse(self):
        """
        L{sip.DigestCalcResponse} is deprecated.
        """
        self.callDeprecated(Version("Twisted", 9, 0, 0),
                            sip.DigestCalcResponse, '', '', '', '', '', '', '',
                            '')

    def test_deprecatedBasicAuthorizer(self):
        """
        L{sip.BasicAuthorizer} is deprecated.
        """
        self.callDeprecated(Version("Twisted", 9, 0, 0), sip.BasicAuthorizer)


    def test_deprecatedDigestAuthorizer(self):
        """
        L{sip.DigestAuthorizer} is deprecated.
        """
        self.callDeprecated(Version("Twisted", 9, 0, 0), sip.DigestAuthorizer)


    def test_deprecatedDigestedCredentials(self):
        """
        L{sip.DigestedCredentials} is deprecated.
        """
        self.callDeprecated(Version("Twisted", 9, 0, 0),
                            sip.DigestedCredentials, '', {}, {})
