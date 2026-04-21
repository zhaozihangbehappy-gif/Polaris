import java.nio.file.Files;
import java.nio.file.Paths;

public class Main {
    public static void main(String[] args) throws Exception {
        if (!Files.exists(Paths.get("lib/helper-lib.jar"))) {
            System.err.println("Could not find artifact: lib/helper-lib.jar");
            System.exit(1);
        }
        System.out.println("Dependency resolved!");
    }
}
