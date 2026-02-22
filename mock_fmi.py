"""Mock FMI WFS response for local testing (RADIATION_MOCK=1).

Scenario: minor incident near the Russian border.
  Helsinki Kumpula   0.55 µSv/h  – elevated
  Espoo Pirttimäki   0.12 µSv/h  – normal
  Vantaa             0.09 µSv/h  – normal
  Lappeenranta       0.72 µSv/h  – elevated (downwind)
  Nuijamaa           8.50 µSv/h  – HIGH
"""

XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection
    xmlns:wfs="http://www.opengis.net/wfs/2.0"
    xmlns:gml="http://www.opengis.net/gml/3.2"
    xmlns:om="http://www.opengis.net/om/2.0"
    xmlns:target="http://xml.fmi.fi/namespace/om/atmosphericfeatures/1.1">

  <target:Location>
    <gml:identifier>100971</gml:identifier>
    <gml:name codeSpace="http://xml.fmi.fi/namespace/locationcode/name">Helsinki Kumpula</gml:name>
    <target:region>Helsinki</target:region>
  </target:Location>

  <target:Location>
    <gml:identifier>101246</gml:identifier>
    <gml:name codeSpace="http://xml.fmi.fi/namespace/locationcode/name">Lappeenranta</gml:name>
    <target:region>Lappeenranta</target:region>
  </target:Location>

  <target:Location>
    <gml:identifier>101256</gml:identifier>
    <gml:name codeSpace="http://xml.fmi.fi/namespace/locationcode/name">Nuijamaa</gml:name>
    <target:region>Lappeenranta</target:region>
  </target:Location>

  <gml:Point gml:id="point-100971"><gml:pos>60.2031 24.9608</gml:pos></gml:Point>
  <gml:Point gml:id="point-101246"><gml:pos>61.0599 28.1885</gml:pos></gml:Point>
  <gml:Point gml:id="point-101256"><gml:pos>61.0748 28.5530</gml:pos></gml:Point>

  <om:resultTime>
    <gml:TimeInstant>
      <gml:timePosition>2026-02-22T09:00:00Z</gml:timePosition>
    </gml:TimeInstant>
  </om:resultTime>

  <gml:doubleOrNilReasonTupleList>
    0.55 0.03  0.72 0.05  8.50 0.42
  </gml:doubleOrNilReasonTupleList>

</wfs:FeatureCollection>
"""
