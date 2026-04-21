import javax.xml.parsers.DocumentBuilder;
import javax.xml.parsers.DocumentBuilderFactory;
import org.xml.sax.SAXParseException;
import java.io.File;

public class PomValidator {
    public static void main(String[] args) {
        try {
            DocumentBuilderFactory factory = DocumentBuilderFactory.newInstance();
            DocumentBuilder builder = factory.newDocumentBuilder();
            builder.parse(new File("pom.xml"));
            System.out.println("POM is valid");
            System.exit(0);
        } catch (SAXParseException e) {
            System.err.println("Non-parseable POM at line " + e.getLineNumber() + ": " + e.getMessage());
            System.exit(1);
        } catch (Exception e) {
            System.err.println("Non-parseable POM: " + e.getMessage());
            System.exit(1);
        }
    }
}
