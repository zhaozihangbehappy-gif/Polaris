public class MemoryExhaustion {
    public static void main(String[] args) {
        java.util.List<byte[]> list = new java.util.ArrayList<>();
        while (true) {
            byte[] chunk = new byte[1024 * 1024];
            list.add(chunk);
        }
    }
}