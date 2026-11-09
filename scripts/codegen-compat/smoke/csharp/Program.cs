// Smoke call for the openapi-generator csharp client (generichost): GET /fixtures.
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using livetennisapi_gen.Api;
using livetennisapi_gen.Client;
using livetennisapi_gen.Extensions;

var builder = Host.CreateApplicationBuilder();
builder.ConfigureApi(options =>
{
    // The spec offers two schemes (bearer or X-API-Key), and the generated
    // DefaultApi will not resolve until a token exists for each of them.
    options.AddTokens(new BearerToken("test-key"));
    options.AddTokens(new ApiKeyToken("test-key", ClientUtils.ApiKeyHeader.X_API_Key, prefix: ""));
    options.AddApiHttpClients(client => client.BaseAddress = new Uri(args[0].TrimEnd('/') + "/"));
});
using var host = builder.Build();
var api = host.Services.GetRequiredService<IDefaultApi>();
var response = await api.ListFixturesAsync(limit: new Option<int>(3));
var page = response.Ok() ?? throw new Exception($"status {response.StatusCode}: {response.RawContent}");
var rows = page.Data ?? throw new Exception(response.RawContent);
var row = rows[0];
if (rows.Count != 3 || row.Tournament != "Rome") throw new Exception(response.RawContent);
Console.WriteLine($"csharp smoke ok: {rows.Count} fixtures, first {row.Player1Name} v {row.Player2Name}");
