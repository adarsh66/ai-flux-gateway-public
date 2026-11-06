// Installed Roslyn + Newtonsoft references only. No package restore or network.
using System;
using System.IO;
using System.Linq;
using System.Text;
using System.Text.Json;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;

public static class Resume06Native {
    public static int Main(string[] args) {
        if (args[0] == "verify") {
            using var doc = JsonDocument.Parse(File.ReadAllBytes(args[1]));
            var root = doc.RootElement;
            var certBytes = Convert.FromBase64String(root.GetProperty("certificate").GetString());
            if (Convert.ToHexString(SHA256.HashData(certBytes)).ToLowerInvariant() != args[2]) return 2;
            using var certificate = new X509Certificate2(certBytes);
            using var key = certificate.GetRSAPublicKey();
            using var input = new MemoryStream();
            Console.OpenStandardInput().CopyTo(input);
            bool valid = key != null && key.KeySize >= 2048 && key.VerifyData(input.ToArray(),
                Convert.FromBase64String(root.GetProperty("signature").GetString()),
                HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
            if (valid) Console.Write("VERIFIED");
            return valid ? 0 : 2;
        }
        var expressions = JsonSerializer.Deserialize<string[]>(File.ReadAllText(args[1]));
        var references = Directory.GetFiles(args[2], "*.dll").Select(p => MetadataReference.CreateFromFile(p))
            .Concat(new[] { MetadataReference.CreateFromFile(args[3]) }).ToArray();
        // Typed APIM contract fixture. This compiles every expression, including
        // the entire real Newtonsoft scorer/PII/usage code, not dynamic syntax.
        string fixture = @"
using System; using System.Linq; using System.Text; using System.Collections.Generic;
using System.Text.RegularExpressions; using Newtonsoft.Json; using Newtonsoft.Json.Linq;
public interface IMessageBody { T As<T>(bool preserveContent = false); }
public interface IResponse { int StatusCode {get;} IMessageBody Body {get;}
    IReadOnlyDictionary<string,string[]> Headers {get;} }
public class Url { public string Path {get;set;} public IReadOnlyDictionary<string,string[]> Query {get;set;} }
public class Request { public string Method {get;set;} public string IpAddress {get;set;}
    public Url Url {get;set;} public Url OriginalUrl {get;set;} public IMessageBody Body {get;set;}
    public IReadOnlyDictionary<string,string[]> Headers {get;set;} }
public class Api { public string Id {get;set;} public string Revision {get;set;} }
public class Identity { public string Id {get;set;} }
public class LastError { public string Source {get;set;} public string Reason {get;set;} public string PolicyId {get;set;} }
public class Context { public Api Api {get;set;} public Identity Subscription {get;set;}
    public Identity Product {get;set;} public Request Request {get;set;} public IResponse Response {get;set;}
    public Guid RequestId {get;set;} public LastError LastError {get;set;}
    public IReadOnlyDictionary<string,object> Variables {get;set;} }
public static class ApimExtensions {
    public static string GetValueOrDefault(this IReadOnlyDictionary<string,string[]> values, string key, string fallback) {
        return values.TryGetValue(key, out var item) ? string.Join("","", item) : fallback;
    }
    public static T GetValueOrDefault<T>(this IReadOnlyDictionary<string,object> values, string key, T fallback) {
        return values.TryGetValue(key, out var item) ? (T)item : fallback;
    }
}
public class Expressions {
";
        var source = new StringBuilder(fixture);
        for (int i = 0; i < expressions.Length; i++) {
            var item = expressions[i];
            var body = item.StartsWith("@(") ? "return " + item.Substring(2, item.Length - 3) + ";"
                : item.Substring(2, item.Length - 3);
            source.Append("public object F" + i + "(Context context) { " + body + " }\n");
        }
        source.Append("}");
        var tree = CSharpSyntaxTree.ParseText(source.ToString(), new CSharpParseOptions(LanguageVersion.CSharp7_3));
        var compilation = CSharpCompilation.Create("Resume06Expressions", new[] { tree }, references,
            new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary));
        using var output = new MemoryStream();
        var result = compilation.Emit(output);
        var errors = result.Diagnostics.Where(d => d.Severity == DiagnosticSeverity.Error).ToArray();
        foreach (var error in errors) Console.WriteLine(error.ToString());
        Console.WriteLine(JsonSerializer.Serialize(new { expressions = expressions.Length,
            semantic_errors = errors.Length, typed_context = true, full_newtonsoft = true,
            apim_service_validation = "NOT_EXECUTED_FIRST_POLICY_PUT_BEFORE_ONLINE" }));
        return result.Success ? 0 : 1;
    }
}