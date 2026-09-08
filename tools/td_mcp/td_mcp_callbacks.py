# TouchDesigner as compute support, over MCP.
#
# This is the callbacks DAT of a Web Server DAT inside TouchDesigner. It speaks the
# Model Context Protocol's Streamable HTTP transport (JSON-RPC over POST) on /mcp, so
# Claude Code can be pointed at it with
#
#     claude mcp add --transport http touchdesigner http://localhost:9988/mcp
#
# and a plain /run endpoint for scripts (curl, python) in the same session. Nothing
# here is downloaded: it is the project's own code, ~200 lines, all readable.
#
# Tools:
#   td_run       exec Python inside TD; whatever the code assigns to `result` comes back
#   td_list      operators under a parent, filtered by a glob
#   td_inspect   an operator: type, parameters, connections, CHOP/DAT/TOP summary
#   td_chop      a CHOP's channels as arrays
#   td_snapshot  save a TOP to a PNG / JPG / EXR on disk
#
# Everything runs on TD's main thread, in the frame the request lands in.

import io
import json
import traceback

MCP_PROTOCOL = '2025-03-26'
SERVER_INFO = {'name': 'touchdesigner', 'version': '0.1.0'}

TOOLS = [
    {
        'name': 'td_run',
        'description': 'Execute Python inside the running TouchDesigner (td module, op(), me, project '
                       'are in scope). Assign to `result` to return a value; stdout is returned too.',
        'inputSchema': {'type': 'object', 'properties': {'code': {'type': 'string'}}, 'required': ['code']},
    },
    {
        'name': 'td_list',
        'description': 'List operators under a parent path (default /), matching a glob pattern (default *).',
        'inputSchema': {'type': 'object', 'properties': {
            'parent': {'type': 'string'}, 'pattern': {'type': 'string'}, 'depth': {'type': 'integer'}}},
    },
    {
        'name': 'td_inspect',
        'description': 'Describe one operator: family, type, parameters with values, inputs/outputs, and a '
                       'summary of its data (channels, table size, texture size).',
        'inputSchema': {'type': 'object', 'properties': {'path': {'type': 'string'}}, 'required': ['path']},
    },
    {
        'name': 'td_chop',
        'description': 'Read a CHOP: channel names and sample arrays (capped at max_samples per channel).',
        'inputSchema': {'type': 'object', 'properties': {
            'path': {'type': 'string'}, 'max_samples': {'type': 'integer'}}, 'required': ['path']},
    },
    {
        'name': 'td_snapshot',
        'description': 'Save a TOP to an image file (png/jpg/exr/tif by extension) and return the path.',
        'inputSchema': {'type': 'object', 'properties': {
            'path': {'type': 'string'}, 'file': {'type': 'string'}}, 'required': ['path', 'file']},
    },
]


# --------------------------------------------------------------------------- tools
def tool_run(code):
    scope = {'op': op, 'me': me, 'project': project, 'absTime': absTime, 'td': td, 'result': None}
    buffer = io.StringIO()
    import contextlib
    with contextlib.redirect_stdout(buffer):
        exec(code, scope)
    out = {'stdout': buffer.getvalue()}
    value = scope.get('result')
    try:
        json.dumps(value)
        out['result'] = value
    except (TypeError, ValueError):
        out['result'] = repr(value)
    return out


def tool_list(parent='/', pattern='*', depth=1):
    root = op(parent)
    if root is None:
        raise ValueError('no operator at ' + parent)
    rows = []
    for child in root.findChildren(name=pattern, maxDepth=max(1, int(depth or 1))):
        rows.append({'path': child.path, 'type': child.OPType, 'family': child.family})
    return {'parent': root.path, 'count': len(rows), 'operators': rows}


def tool_inspect(path):
    target = op(path)
    if target is None:
        raise ValueError('no operator at ' + path)
    pars = []
    for par in target.pars():
        try:
            pars.append({'name': par.name, 'label': par.label, 'value': par.eval() if par.style != 'Python' else par.val,
                         'mode': str(par.mode).split('.')[-1]})
        except Exception as error:  # noqa: BLE001 — a parameter that cannot evaluate is still listed
            pars.append({'name': par.name, 'error': str(error)})
    info = {
        'path': target.path, 'type': target.OPType, 'family': target.family,
        'inputs': [i.path for i in target.inputs], 'outputs': [o.path for o in target.outputs],
        'pars': pars,
    }
    if target.family == 'CHOP':
        info['channels'] = [c.name for c in target.chans()]
        info['numSamples'] = target.numSamples
        info['rate'] = target.rate
    elif target.family == 'TOP':
        info['width'] = target.width
        info['height'] = target.height
    elif target.family == 'DAT':
        info['numRows'] = target.numRows
        info['numCols'] = target.numCols
    return info


def tool_chop(path, max_samples=4096):
    target = op(path)
    if target is None or target.family != 'CHOP':
        raise ValueError('no CHOP at ' + str(path))
    cap = max(1, int(max_samples or 4096))
    channels = {}
    for chan in target.chans():
        channels[chan.name] = [float(v) for v in chan.vals[:cap]]
    return {'path': target.path, 'rate': target.rate, 'numSamples': target.numSamples, 'channels': channels}


def tool_snapshot(path, file):
    target = op(path)
    if target is None or target.family != 'TOP':
        raise ValueError('no TOP at ' + str(path))
    saved = target.save(file)
    return {'path': target.path, 'file': saved, 'width': target.width, 'height': target.height}


HANDLERS = {
    'td_run': lambda a: tool_run(a['code']),
    'td_list': lambda a: tool_list(a.get('parent', '/'), a.get('pattern', '*'), a.get('depth', 1)),
    'td_inspect': lambda a: tool_inspect(a['path']),
    'td_chop': lambda a: tool_chop(a['path'], a.get('max_samples', 4096)),
    'td_snapshot': lambda a: tool_snapshot(a['path'], a['file']),
}


# ------------------------------------------------------------------------ JSON-RPC
def rpc_result(id_, result):
    return {'jsonrpc': '2.0', 'id': id_, 'result': result}


def rpc_error(id_, code, message):
    return {'jsonrpc': '2.0', 'id': id_, 'error': {'code': code, 'message': message}}


def handle_rpc(message):
    method = message.get('method')
    id_ = message.get('id')
    params = message.get('params') or {}
    if method == 'initialize':
        return rpc_result(id_, {'protocolVersion': MCP_PROTOCOL, 'capabilities': {'tools': {}}, 'serverInfo': SERVER_INFO})
    if method == 'ping':
        return rpc_result(id_, {})
    if method == 'tools/list':
        return rpc_result(id_, {'tools': TOOLS})
    if method == 'tools/call':
        name = params.get('name')
        handler = HANDLERS.get(name)
        if handler is None:
            return rpc_error(id_, -32602, 'unknown tool ' + str(name))
        try:
            value = handler(params.get('arguments') or {})
            return rpc_result(id_, {'content': [{'type': 'text', 'text': json.dumps(value, default=str)}], 'isError': False})
        except Exception:  # noqa: BLE001 — the traceback is the tool's answer
            return rpc_result(id_, {'content': [{'type': 'text', 'text': traceback.format_exc()}], 'isError': True})
    if method and method.startswith('notifications/'):
        return None
    return rpc_error(id_, -32601, 'method not found: ' + str(method))


def body_of(request):
    data = request.get('data', b'')
    if isinstance(data, bytes):
        return data.decode('utf-8', 'replace')
    return str(data)


def reply(response, status, payload, content_type='application/json'):
    response['statusCode'] = status
    response['statusReason'] = {200: 'OK', 202: 'Accepted', 400: 'Bad Request', 404: 'Not Found', 405: 'Method Not Allowed'}.get(status, 'OK')
    response['Content-Type'] = content_type
    response['Access-Control-Allow-Origin'] = '*'
    response['data'] = payload if isinstance(payload, str) else json.dumps(payload, default=str)
    return response


# ------------------------------------------------------------- Web Server DAT hooks
def onHTTPRequest(webServerDAT, request, response):
    uri = request.get('uri', '/')
    method = request.get('method', 'GET').upper()
    if uri.startswith('/mcp'):
        if method == 'GET':
            return reply(response, 405, {'error': 'this server answers JSON-RPC over POST only; no event stream'})
        if method == 'DELETE':
            return reply(response, 200, {'ok': True})
        try:
            message = json.loads(body_of(request) or '{}')
        except ValueError:
            return reply(response, 400, rpc_error(None, -32700, 'parse error'))
        messages = message if isinstance(message, list) else [message]
        answers = [a for a in (handle_rpc(m) for m in messages) if a is not None]
        if not answers:
            return reply(response, 202, '')
        return reply(response, 200, answers[0] if not isinstance(message, list) else answers)
    if uri.startswith('/run') and method == 'POST':
        try:
            return reply(response, 200, tool_run(body_of(request)))
        except Exception:  # noqa: BLE001
            return reply(response, 200, {'error': traceback.format_exc()})
    if uri == '/' or uri.startswith('/health'):
        return reply(response, 200, {
            'server': SERVER_INFO, 'mcp': '/mcp', 'run': '/run', 'build': app.build, 'project': project.name,
            'tools': [t['name'] for t in TOOLS],
        })
    return reply(response, 404, {'error': 'not found', 'uri': uri})


def onWebSocketOpen(webServerDAT, client, uri):
    return


def onWebSocketClose(webServerDAT, client):
    return


def onWebSocketReceiveText(webServerDAT, client, data):
    return


def onWebSocketReceiveBinary(webServerDAT, client, data):
    return


def onServerStart(webServerDAT):
    return


def onServerStop(webServerDAT):
    return
