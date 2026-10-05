// Agent sandbox relay (WP-4.7). The one container on the internal sandbox
// network with a route out: each "port=host:port" argument listens on port and
// forwards bytes to that one gateway target. Nothing else is reachable from a
// sandboxed agent.
import net from 'node:net';

const routes = process.argv.slice(2).map((spec) => {
  const match = /^(\d+)=([^:]+):(\d+)$/.exec(spec);
  if (!match) {
    console.error(`invalid route ${spec}; expected port=host:port`);
    process.exit(2);
  }
  return { listen: Number(match[1]), host: match[2], port: Number(match[3]) };
});
if (routes.length === 0) {
  console.error('no routes given');
  process.exit(2);
}

for (const route of routes) {
  const server = net.createServer((client) => {
    const upstream = net.connect(route.port, route.host);
    client.pipe(upstream);
    upstream.pipe(client);
    const close = () => {
      client.destroy();
      upstream.destroy();
    };
    client.on('error', close);
    upstream.on('error', close);
    client.on('close', close);
    upstream.on('close', close);
  });
  server.listen(route.listen, '0.0.0.0', () => {
    console.log(`relay ${route.listen} -> ${route.host}:${route.port}`);
  });
}
