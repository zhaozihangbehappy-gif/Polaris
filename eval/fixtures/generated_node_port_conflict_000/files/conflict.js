const net = require("node:net");

const port = 3000;
const host = "127.0.0.1";

const first = net.createServer();
const second = net.createServer();

first.listen(port, host, () => {
  second.listen(port, host, () => {
    second.close();
    first.close();
  });
});
