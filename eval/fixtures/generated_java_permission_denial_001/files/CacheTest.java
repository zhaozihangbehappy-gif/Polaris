import java.io.File;
import java.io.FileWriter;
import java.io.IOException;

public class CacheTest {
    public static void main(String[] args) {
        File cacheDir = new File(".gradle");
        File cacheFile = new File(cacheDir, "cachefile.txt");

        try {
            cacheDir.mkdirs();
            FileWriter writer = new FileWriter(cacheFile);
            writer.write("test");
            writer.close();
            System.out.println("Success");
        } catch (IOException e) {
            System.err.println("Permission denied .gradle: " + e.getMessage());
            System.exit(1);
        }
    }
}
