# Run this once in TouchDesigner's textport (Alt+T):
#
#     exec(open(r'D:/School/sciarc/ATStudioTwo/MusicToArchitecture/tools/td_mcp/bootstrap.py').read())
#
# It builds /mcp — a Base COMP holding the callbacks DAT and a Web Server DAT on port
# 9988 — and saves the project as tools/td_mcp/mcp_host.toe, so from then on
#
#     "C:/Program Files/Derivative/TouchDesigner/bin/TouchDesigner.exe" tools/td_mcp/mcp_host.toe
#
# starts a TouchDesigner that already answers on http://localhost:9988/.

import os

HERE = r'D:/School/sciarc/ATStudioTwo/MusicToArchitecture/tools/td_mcp'
PORT = 9988

root = op('/')
host = root.op('mcp') or root.create(baseCOMP, 'mcp')
host.nodeX, host.nodeY = 0, 400

callbacks = host.op('mcp_callbacks') or host.create(textDAT, 'mcp_callbacks')
with open(os.path.join(HERE, 'td_mcp_callbacks.py'), encoding='utf-8') as handle:
    callbacks.text = handle.read()
callbacks.nodeX, callbacks.nodeY = 0, 0

server = host.op('mcp_server') or host.create(webserverDAT, 'mcp_server')
server.nodeX, server.nodeY = 250, 0
server.par.active = False
server.par.port = PORT
server.par.callbacks = 'mcp_callbacks'
server.par.active = True

project.save(os.path.join(HERE, 'mcp_host.toe'))
print('td_mcp: serving on http://localhost:%d/ (mcp at /mcp) - saved %s' % (PORT, os.path.join(HERE, 'mcp_host.toe')))
