public class Hello {
    public static void main(String[] args) {
        String javaHome = System.getenv("JAVA_HOME");
        if (javaHome == null) {
            System.err.println("JAVA_HOME is not set");
            System.exit(1);
        }
        System.out.println("Hello, World!");
    }
}