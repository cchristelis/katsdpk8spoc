"""This module contains the SDP Product Controller webserver.

We are expecting this to be run as follows:

python controller_server.py ARGO_TOKEN ARGO_BASE_URL
"""
# PoC Master controller
import sys
import asyncio
import pprint

# import logging
import aiohttp
from aiohttp import web
from aiohttp_swagger3 import SwaggerDocs, SwaggerUiSettings

from .workflow_controller import ProductControllerWorkflow


ARGO_TOKEN = sys.argv[-2]
ARGO_BASE_URL = sys.argv[-1]


def dict2html(data: dict):
    html = "<pre>" + pprint.pformat(data) + "</pre>"
    return html


def html_page(name: str, subarray: int, body: str = "", data: dict = None):
    html = "<html><body>"
    html += "<h1>{} subarray{}</h1>".format(name.title(), subarray)
    html += "<form action='/'><input type='submit' value='Home'></form>"
    if name != "status":
        html += "<form action='/status'>"
        html += "<input type='hidden' name='subarray' value='{}'>".format(subarray)
        html += "<input type='submit' value='Status'></form>"
    if body:
        html += "</br><div>"
        html += body
        html += "</div></br>"
    if data:
        html += "</br><div>"
        html += dict2html(data)
        html += "</div></br>"
    html += "</body></html>"
    return html


async def argo_post(url, headers=None, data=None):
    """Post an ARGO JSON to an URL"""
    headers = headers or {}
    headers["content-type"] = "application/json"
    async with aiohttp.ClientSession() as session:
        resp = await session.post(url, json=data, headers=headers)
        data = await resp.json()
    return data


async def argo_get(url, headers=None):
    """Get an ARGO Json to an URL"""
    async with aiohttp.request("GET", url, headers=headers) as resp:
        assert resp.status == 200
        data = await resp.json()
    return data


async def start_subarray(subarray: int, receptors: int):
    """Start a subarray with a given number as well as number of receptors

    :param subarray: Subarray number.
    :param receptors: Receptor number
    :return: status of the created workflow
    """
    wf = ProductControllerWorkflow(subarray, receptors)
    workflow_dict = {
        "serverDryRun": False,
        "namespace": f"sdparray{subarray}",
        "workflow": wf.generate()
    }
    url = "{}/api/v1/workflows/sdparray{}".format(ARGO_BASE_URL, subarray)
    status = await argo_post(url, data=workflow_dict)
    return {"status": status, "workflow": workflow_dict}


async def stop_workflow(subarray: int, workflow_name: str):
    """Stop a subarray with

    :param subarray: subarray number
    :param workflow_name: workflow name
    :return: status of the stop request
    """
    _headers = {"content-type": "application/json"}
    url = "{}/api/v1/workflows/sdparray{}/{}/terminate".format(ARGO_BASE_URL, subarray, workflow_name)
    data = {
        "name": workflow_name,
        "namespace": "sdparray{}".format(subarray),
    }
    async with aiohttp.ClientSession() as session:
        resp = await session.put(url, json=data, headers=_headers)
        # assert resp.status == 200
        data = await resp.json()
    return data


async def subarray_status(subarray: int):
    url = f"{ARGO_BASE_URL}/api/v1/workflows/sdparray{subarray}"
    headers = {"Authorization": ARGO_TOKEN}
    return await argo_get(url, headers)


async def start_handle(request):
    """
    ---
    description: start a subarray
    parameters:
       - in: query
         name: subarray
         schema:
           type: integer
         required: true
         description: The subarray ID.
       - in: query
         name: receptors
         schema:
           type: integer
         required: true
         description: The number of receptors in the subarray.
    responses:
        "200":
            $ref: '#/components/responses/Reply200Ack'
        "405":
            $ref: '#/components/responses/HTTPMethodNotAllowed'
        "421":
            $ref: '#/components/responses/HTTPMisdirectedRequest'
        "422":
            $ref: '#/components/responses/HTTPUnprocessableEntity'
    """
    response = await start_subarray(
        request.query["subarray"], request.query["receptors"]
    )
    buf = html_page("start", request.query["subarray"], data=response)
    return web.Response(body=buf, content_type="text/html")


async def stop_handle(request):
    """
    ---
    description: stop a subarray
    parameters:
       - in: query
         name: subarray
         schema:
           type: integer
         required: true
         description: The subarray ID.
    responses:
        "200":
            $ref: '#/components/responses/Reply200Ack'
        "405":
            $ref: '#/components/responses/HTTPMethodNotAllowed'
        "421":
            $ref: '#/components/responses/HTTPMisdirectedRequest'
        "422":
            $ref: '#/components/responses/HTTPUnprocessableEntity'
    """
    status = await subarray_status(request.query["subarray"])
    items = status.get("items")
    info = []
    if items:
        for wf in items:
            res = await stop_workflow(request.query["subarray"], wf["metadata"]["name"])
            info.append(res)

    buf = html_page("stop", subarray=request.query["subarray"], data=info)
    return web.Response(body=buf, content_type="text/html")


async def status_handle(request):
    """
    ---
    description: status a subarray
    parameters:
       - in: query
         name: subarray
         schema:
           type: integer
         required: true
         description: The subarray ID.
    responses:
        "200":
            $ref: '#/components/responses/Reply200Ack'
        "405":
            $ref: '#/components/responses/HTTPMethodNotAllowed'
        "421":
            $ref: '#/components/responses/HTTPMisdirectedRequest'
        "422":
            $ref: '#/components/responses/HTTPUnprocessableEntity'
    """
    data = await subarray_status(request.query["subarray"])
    buf = html_page("status", request.query["subarray"], data=data)
    return web.Response(body=buf, content_type="text/html")


async def map_page(request):
    with open("index.html") as fh:
        text = fh.read()
    return web.Response(text=text.strip(), content_type="text/html")


async def status_runner(app):
    while True:
        await asyncio.sleep(1)


async def start_background_tasks(app):
    app["status_runner"] = asyncio.Task(status_runner(app))


app = web.Application()
# app["status_obj"] = SdpPcStatus()
app.on_startup.append(start_background_tasks)


if __name__ == "__main__":
    swagger = SwaggerDocs(
        app,
        swagger_ui_settings=SwaggerUiSettings(path="/api/doc"),
        title="Product controller PoC",
        version="1.0.0",
        # components="swagger.yaml",
    )
    swagger.add_routes(
        [
            web.get("/", map_page),
            web.get("/start", start_handle),
            web.get("/stop", stop_handle),
            web.get("/status", status_handle),
        ]
    )
    web.run_app(app)
