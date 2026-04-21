import java.nio.file.*;

public class CacheManager {
    public static void main(String[] args) throws Exception {
        String cacheDir = "/dev/.m2/repository";
        Files.createDirectories(Paths.get(cacheDir));
        Files.write(
            Paths.get(cacheDir + "/cached-lib.jar"),
            "cached data".getBytes()
        );
        System.out.println("Cache stored successfully");
    }
}
