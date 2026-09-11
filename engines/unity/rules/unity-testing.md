paths:
  - "Assets/Tests/**"
  - "Assets/**/*Tests*.cs"
  - "Assets/**/*Test.cs"
---

# Unity Testing — Never Let Build Output Land Under `Assets/`

Unity imports any managed DLL under `Assets/` as a plugin, and asmdefs bind
`precompiledReferences` **by filename**: a `dotnet build` writing inside `Assets/` replaces
Unity's dependencies, and the errors appear inside `Library/PackageCache/`.

## Detection — run first

```bash
find assets -iname "*.dll"                        # both must return nothing
find assets -type d \( -name bin -o -name obj \)
```

A hit **is** the bug: fix the output path before reading package source. Delete any stale
`bin/`/`obj/` under `assets/` *and* its `.meta` files, then reimport.

## Fix — keep dotnet output out of the tree

`Greenwood.Sim.Tests.csproj` pins these; every csproj under `Assets/` must:

```xml
<BaseOutputPath>..\..\..\tests-out\Greenwood.Sim.Tests\</BaseOutputPath>
<BaseIntermediateOutputPath>..\..\..\tests-out\Greenwood.Sim.Tests\obj\</BaseIntermediateOutputPath>
```

`tests-out/` is gitignored; **never remove these**. `dotnet test` is unaffected.

## Do not override `com.unity.test-framework`

1.7.0 on 6000.5.6f1 compiles clean. **A local copy of its source cannot work** —
`InternalsVisibleTo` names `UnityEngine.TestRunner` / `UnityEditor.TestRunner` exactly, so an
override collides or loses the grant. Never copy, patch or delete package source; diff the
Editor's `BuiltInPackages` copy first. Restoring one you damaged: deleting
`Library/PackageCache/<pkg>@<hash>/` is not enough — also delete
`Library/PackageManager/{ProjectCache,ProjectCache.md5,projectResolution.json}`. Leave
`Packages/packages-lock.json`.

## Test code

NUnit 4, constraint model: `Assert.That(x, Is.EqualTo(y))`, `Is.LessThan`, `Assert.Throws<T>`;
`[UnityTest]`/`[UnitySetUp]`/`[UnityTearDown]` from TestTools return `IEnumerator`;
`LogAssert.Expect`/`NoUnexpectedReceived`. Gone in NUnit 4:
`Assert.Less`/`Greater` (use `Is.LessThan`), `Assert.IsNullOrEmpty` (use `Is.Null.Or.Empty`).
`UnityEngine.Assertions.Assert` lacks `Less`, `Greater`, `Throws` — alias when both are used.

## Test asmdef shape

`UnityEngine.TestTools` is a namespace, not an assembly; in `references` it is a no-op.

```json
{ "references": [ "UnityEngine.TestRunner", "UnityEditor.TestRunner" ],
  "overrideReferences": true,
  "precompiledReferences": [ "nunit.framework.dll" ],
  "defineConstraints": [ "UNITY_INCLUDE_TESTS" ] }
```

## Verification and running suites

The host watchdog kills backgrounded batchmode runs. **Run suites in the foreground, one at a
time**, after `dotnet build-server shutdown`:

```bash
U="C:/Program Files/Unity/Hub/Editor/6000.5.6f1/Editor/Unity.exe"
# empty = toolchain intact
"$U" -batchmode -nographics -quit -projectPath . -logFile - 2>&1 | grep "error CS" | grep PackageCache
timeout 600 "$U" -batchmode -nographics -quit -projectPath . -logFile - \
  -executeMethod Greenwood.Build.CI.RunEditModeTests
# then, once done: CI.RunPlayModeTests
```

Background: docs/engineering-notes/unity-testing.md
