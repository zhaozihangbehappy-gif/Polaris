import com.sun.net.httpserver.*;
import java.net.*;
import java.io.*;
import java.util.concurrent.atomic.AtomicInteger;

public class Main {
    static HttpServer server;
    static AtomicInteger requestCount = new AtomicInteger(0);

    static void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress(9999), 0);
        server.createContext("/test", exchange -> {
            int count = requestCount.incrementAndGet();
            if (count == 1) {
                exchange.sendResponseHeaders(503, 0);
            } else {
                exchange.sendResponseHeaders(200, 2);
                exchange.getResponseBody().write("OK".getBytes());
            }
            exchange.close();
        });
        server.setExecutor(null);
        server.start();
    }

    static void stopServer() {
        server.stop(1);
    }

    static boolean client() throws IOException {
        URL url = new URL("http://localhost:9999/test");
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setConnectTimeout(2000);
        int responseCode = conn.getResponseCode();
        conn.disconnect();

        if (responseCode != 200) {
            System.err.println("Received status code " + responseCode + " from server");
            return false;
        }
        return true;
    }

    public static void main(String[] args) throws Exception {
        startServer();
        Thread.sleep(500);

        try {
            boolean success = client();
            System.exit(success ? 0 : 1);
        } finally {
            stopServer();
        }
    }
}
