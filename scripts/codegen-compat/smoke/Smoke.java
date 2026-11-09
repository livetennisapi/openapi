// Smoke call for the openapi-generator java client: GET /fixtures.
import org.openapitools.client.ApiClient;
import org.openapitools.client.api.DefaultApi;
import org.openapitools.client.auth.HttpBearerAuth;
import org.openapitools.client.model.Fixture;
import org.openapitools.client.model.ListFixtures200Response;

public class Smoke {
    public static void main(String[] args) throws Exception {
        ApiClient client = new ApiClient();
        client.setBasePath(args[0]);
        ((HttpBearerAuth) client.getAuthentication("bearerAuth")).setBearerToken("test-key");
        ListFixtures200Response page = new DefaultApi(client).listFixtures(null, null, null, null, 3, null);
        Fixture row = page.getData().get(0);
        if (page.getData().size() != 3 || !"Rome".equals(row.getTournament())) {
            throw new IllegalStateException(page.toString());
        }
        System.out.println("java smoke ok: " + page.getData().size() + " fixtures, first "
                + row.getPlayer1Name() + " v " + row.getPlayer2Name());
    }
}
