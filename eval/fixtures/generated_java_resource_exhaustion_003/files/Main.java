public class Main {
    public static void main(String[] args) {
        infiniteRecursion(0);
    }

    static void infiniteRecursion(int n) {
        infiniteRecursion(n + 1);
    }
}
