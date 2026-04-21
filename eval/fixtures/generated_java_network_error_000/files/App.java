import java.net.Socket;
import java.io.IOException;

public class App {
    public static void main(String[] args) {
        int port = Integer.parseInt(args[0]);
        try {
            Socket socket = new Socket("127.0.0.1", port);
            socket.close();
            System.out.println("Downloaded successfully");
        } catch (IOException e) {
            System.err.println("Could not transfer artifact: Connection refused");
            System.exit(1);
        }
    }
}
