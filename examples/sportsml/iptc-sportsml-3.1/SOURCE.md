# IPTC SportsML 3.1 schema files

These 14 files are IPTC's SportsML 3.1 schema, copied unchanged.

- Source: https://www.iptc.org/std/SportsML/3.1/specification/
- Fetched: 2026-11-15
- Also in IPTC's official package https://www.iptc.org/std/SportsML/SportsML_3.1.zip, with the same bytes
- Version: SportsML 3.1, released by IPTC in June 2019 (https://iptc.org/standards/sportsml-g2/)
- Entry point: `sportsml.xsd`. It includes the tennis plugin `sportsml-specific-tennis.xsd`, the other sport plugins and NewsML-G2 2.22. `xml.xsd` is the W3C schema for the XML namespace.

## Licence

Copyright IPTC, the International Press Telecommunications Council, www.iptc.org.

Each IPTC file says in its header that it is published under the Creative Commons Attribution 4.0 licence.
The licence is at https://creativecommons.org/licenses/by/4.0/.

The files also end with IPTC's older specification licence agreement, kept as published. `xml.xsd` is published by the W3C.

These copies are here only so `../check_fixtures.py` can validate the fixtures offline. The Live Tennis API project did not write them, and IPTC has not reviewed this folder.

## SHA-256

```
ea31ca7189762cb8a19402a5dd831be3652270e3576d8704577b4f1b9f308899  NewsML-G2_2.22-spec-All-Power.xsd
d3e35a67274e1e4336e7b0cb2404955aeba053e0e5d675d7f9d8e69350864e75  sportsml-specific-american-football.xsd
b15141c44159d6adf16c8d9a8d57351bb10d95d28f9e6e326ba7219c3be1406c  sportsml-specific-baseball.xsd
7af008dbf358f221806d1c04e1e762b5f674338fd5df6a0a735bb6da8c1ba907  sportsml-specific-basketball.xsd
eee73c4932e8658bacd4a1a35d7d7aafaa7b3bd65ef99804cde3424f85803c5c  sportsml-specific-curling.xsd
9340b91e96a875f008f138fbddaf2b9c89f451f6c317ccb4bd7148801a6fdedc  sportsml-specific-golf.xsd
1a6350bf27b3f9af48e4cee2d88c9a71d25440b2892bb137b8104cc40bf7cd74  sportsml-specific-ice-hockey.xsd
f30a4888e878f8459c26e1ae4852cdbfc086464f3a60890f8b199626951fbbe4  sportsml-specific-motor-racing.xsd
708c15b0f49cc228524bdc0e1c53b9126d0f21fec91052b411470a1f6e59f66c  sportsml-specific-rugby.xsd
f6d4412f710fdad6b9434421b9153b05453d4ae4a3c91f29bb7626c0b016361b  sportsml-specific-soccer.xsd
1c76a0f9a6ef9907025975e1e63b90b048c29df0b72e3baeda67d35c65ea0cf3  sportsml-specific-tennis.xsd
4b62d65ee719a85dd5fdebdabf0304d67c608af68691dd610047d1d741f5a5ec  sportsml-specific-volleyball.xsd
7948f1ba12901afb228619c534a54eae2eb6f43c932e08a269df7fb431623a84  sportsml.xsd
87557312725ea4a6615729711f9e841b9edf3445ab03c9765e65127ba4ffb529  xml.xsd
```
