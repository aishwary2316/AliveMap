import json

import httpx
import pytest

from laptop.endpoint import endpoint
from laptop.playground_client import PlaygroundClient


def test_https_private_configuration_and_override_do_not_leak_to_loopback(tmp_path,monkeypatch):
    for name in ('ALIVEMAP_MEC_URL','CF_ACCESS_CLIENT_ID','CF_ACCESS_CLIENT_SECRET'):
        monkeypatch.delenv(name,raising=False)
    path=tmp_path/'endpoint.json'
    path.write_text(json.dumps({'url':'https://alivemap.aishtrex.com','access_client_id':'test-id','access_client_secret':'test-secret'}))
    url, headers=endpoint(config_path=path)
    assert url=='https://alivemap.aishtrex.com' and headers['CF-Access-Client-Secret']=='test-secret'
    assert endpoint('http://127.0.0.1:18767',path)[1]=={}
    monkeypatch.setenv('ALIVEMAP_MEC_URL','https://alternate.example')
    assert endpoint(config_path=path)[0]=='https://alternate.example'
    assert endpoint('https://explicit.example',path)[0]=='https://explicit.example'
    assert endpoint('https://explicit.example',path)[1]=={}


@pytest.mark.parametrize('url',['http://mec.example','ftp://mec.example','https://id:secret@mec.example','https://mec.example?token=secret','https://mec.example/#secret','https://mec.example/api'])
def test_unsafe_endpoint_shapes_rejected(url,tmp_path):
    with pytest.raises(ValueError):endpoint(url,tmp_path/'absent.json')


def test_https_client_verifies_certificates_and_does_not_follow_redirects(tmp_path,monkeypatch):
    from laptop import endpoint as config
    monkeypatch.setattr(config,'CONFIG',tmp_path/'absent.json')
    monkeypatch.setenv('CF_ACCESS_CLIENT_ID','test-id')
    monkeypatch.setenv('CF_ACCESS_CLIENT_SECRET','test-secret')
    calls=[]
    class Capture(httpx.Client):
        def __init__(self,**kwargs):
            calls.append(kwargs)
            super().__init__(**kwargs)
    monkeypatch.setattr('laptop.playground_client.httpx.Client',Capture)
    client=PlaygroundClient('https://alivemap.aishtrex.com','epoch','map',[0,0,1,1],[])
    client.close()
    assert calls[0]['verify'] is True and calls[0]['follow_redirects'] is False
    assert calls[0]['headers']['CF-Access-Client-Id']=='test-id'


def test_transient_transport_and_5xx_retry_without_repeating_auth_errors(monkeypatch):
    responses=iter([503,200,401])
    calls=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(next(responses),json={'ok':True})
    http=httpx.Client(base_url='https://example.test',transport=httpx.MockTransport(respond))
    client=PlaygroundClient(None,'epoch','map',[0,0,1,1],[],http=http)
    monkeypatch.setattr('laptop.playground_client.time.sleep',lambda _:None)
    assert client.request('GET','/health').status_code==200 and len(calls)==2
    assert client.request('GET','/health').status_code==401 and len(calls)==3
    client.close()


def test_persistent_outage_has_only_one_short_retry(monkeypatch):
    calls=[];sleeps=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(530)
    http=httpx.Client(base_url='https://example.test',transport=httpx.MockTransport(respond))
    client=PlaygroundClient(None,'epoch','map',[0,0,1,1],[],http=http)
    monkeypatch.setattr('laptop.playground_client.time.sleep',sleeps.append)
    with pytest.raises(httpx.HTTPStatusError):client.request('POST','/tick',json={})
    assert len(calls)==2 and sleeps==[.15]
    client.close()
