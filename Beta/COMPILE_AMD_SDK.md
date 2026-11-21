# Guide de Compilation du SDK AMD Ryzen Master

## ⚠️ Important

Le SDK AMD Ryzen Master **n'est pas inclus** dans ce projet. Vous devez l'obtenir directement auprès d'AMD.

## Étape 1: Obtenir le SDK AMD Ryzen Master

### Option A: Via AMD Developer Portal (Officiel)

1. **Créer un compte** sur https://developer.amd.com/
2. **Demander l'accès** au "Ryzen Master SDK"
3. **Télécharger** le SDK une fois approuvé
4. **Extraire** le SDK dans un dossier (ex: `C:\AMDRyzenMasterSDK\`)

### Option B: Via Ryzen Master Application

Le SDK peut être inclus avec l'application Ryzen Master d'AMD:
1. Téléchargez [AMD Ryzen Master](https://www.amd.com/en/technologies/ryzen-master)
2. Installez-le
3. Le SDK peut se trouver dans le dossier d'installation (ex: `C:\Program Files\AMD\AMD Ryzen Master\SDK\`)

## Étape 2: Installer Visual Studio

### Version requise
- Visual Studio 2019 ou 2022 (Community Edition gratuit)

### Composants nécessaires
Lors de l'installation, cochez:
- ✅ **Développement Desktop en C++** (Desktop development with C++)
- ✅ **Windows 10 SDK** (ou Windows 11 SDK)
- ✅ **MSVC v143 - VS 2022 C++ x64/x86 build tools** (ou v142 pour VS 2019)

### Téléchargement
https://visualstudio.microsoft.com/downloads/

## Étape 3: Configurer le projet

### Définir la variable d'environnement

**Méthode 1: Temporaire (session CMD actuelle)**
```cmd
set AMDRMMONITORSDKPATH=C:\Chemin\Vers\AMDRyzenMasterSDK
```

**Méthode 2: Permanente (Windows)**
1. Appuyez sur `Win + R`, tapez `sysdm.cpl`
2. Onglet "Avancé" → "Variables d'environnement"
3. Variables système → Nouveau
4. Nom: `AMDRMMONITORSDKPATH`
5. Valeur: `C:\Chemin\Vers\AMDRyzenMasterSDK`

### Vérifier la structure du SDK

Le dossier du SDK doit contenir:
```
AMDRyzenMasterSDK/
├── include/
│   ├── ICPUEx.h
│   ├── IPlatform.h
│   ├── IDeviceManager.h
│   ├── IBIOSEx.h
│   └── ...
├── lib/
│   ├── Platform.lib
│   └── ...
└── bin/
    ├── AMDRyzenMasterDriver.sys
    ├── AMDRyzenMasterDriver.inf
    └── AMDRyzenMasterDriver.cat
```

## Étape 4: Compiler avec Visual Studio

### Méthode A: Via l'IDE Visual Studio

1. **Ouvrir le projet**:
   - Double-cliquez sur `base\RyzenMasterMonitoringDLL\AMDRyzenMasterMonitoringDLL.sln`
   - Si VS demande de retargeter le projet, acceptez

2. **Configurer le build**:
   - Configuration: **Release**
   - Plateforme: **x64**
   - (En haut de VS, déroulez les menus)

3. **Compiler**:
   - Menu `Build` → `Build Solution` (ou `Ctrl+Shift+B`)

4. **Localiser la DLL**:
   - Elle sera dans: `base\RyzenMasterMonitoringDLL\x64\Release\AMDRyzenMasterMonitoringDLL.dll`

### Méthode B: Via ligne de commande (Developer Command Prompt)

1. **Ouvrir "Developer Command Prompt for VS 2022"**:
   - Menu Démarrer → "Developer Command Prompt for VS 2022"

2. **Naviguer vers le projet**:
   ```cmd
   cd "C:\Users\kinde\Desktop\Desktop\Dev\Python\WallPaper Stats PC\StrangeCat Monitor Py\Beta\base\RyzenMasterMonitoringDLL"
   ```

3. **Compiler**:
   ```cmd
   msbuild AMDRyzenMasterMonitoringDLL.sln /p:Configuration=Release /p:Platform=x64
   ```

4. **La DLL sera générée** dans `x64\Release\`

## Étape 5: Copier la DLL

Une fois compilée, copiez la DLL:

```cmd
copy "base\RyzenMasterMonitoringDLL\x64\Release\AMDRyzenMasterMonitoringDLL.dll" "base\"
```

## Étape 6: Construire l'application

Maintenant que la DLL est en place:

```cmd
cd "C:\Users\kinde\Desktop\Desktop\Dev\Python\WallPaper Stats PC\StrangeCat Monitor Py\Beta"
build.bat
```

Le build.bat détectera automatiquement la DLL et l'inclura dans l'EXE.

## Dépannage

### Erreur: "Cannot open include file 'ICPUEx.h'"

**Cause**: La variable `AMDRMMONITORSDKPATH` n'est pas définie ou incorrecte.

**Solution**:
```cmd
set AMDRMMONITORSDKPATH=C:\Chemin\Vers\AMDRyzenMasterSDK
```

### Erreur: "LINK : fatal error LNK1104: cannot open file 'Platform.lib'"

**Cause**: Le dossier `lib\` du SDK n'est pas trouvé.

**Solution**: Vérifiez que le SDK contient le dossier `lib\` avec `Platform.lib`.

### Erreur: "MSB8040: Spectre-mitigated libraries are required"

**Cause**: Problème avec les paramètres de sécurité VS 2022.

**Solution**:
1. Propriétés du projet → C/C++ → Génération de code
2. Bibliothèques atténuées Spectre: Non
3. Rebuild

### Erreur: "PlatformToolset v143 not found"

**Cause**: Vous n'avez pas VS 2022 installé.

**Solution**:
- Installez VS 2022 avec le workload C++
- OU modifiez le projet pour utiliser v142 (VS 2019):
  - Ouvrez `.vcxproj` dans un éditeur de texte
  - Remplacez `v143` par `v142`

## Alternative: Utiliser sans le SDK AMD

Si vous ne pouvez pas obtenir le SDK AMD, l'application fonctionne parfaitement avec:

### LibreHardwareMonitor (Recommandé)

1. Téléchargez [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases)
2. Lancez-le (optionnel: cochez "Start with Windows")
3. L'application StrangeCat Monitor se connectera automatiquement
4. Vous aurez accès à:
   - Température CPU AMD
   - PPT/EDC/TDC (puissance)
   - Fréquences
   - Tensions
   - Ventilateurs

L'intégration LHM a été améliorée pour extraire les métriques AMD spécifiques sans avoir besoin du SDK officiel.

## Résumé

| Méthode | Avantages | Inconvénients |
|---------|-----------|---------------|
| **SDK AMD officiel** | Accès complet à toutes les métriques, direct du hardware | Difficile à obtenir, nécessite compilation, admin requis |
| **LibreHardwareMonitor** | Facile à installer, fonctionne sans admin, métriques AMD disponibles | Dépend d'une application externe, légère latence |
| **Sans aucun** | Fonctionne immédiatement, pas de dépendances | Pas de métriques AMD avancées (PPT/EDC/TDC) |

## Contact

Si vous avez des problèmes:
- Vérifiez la documentation AMD Ryzen Master SDK
- Consultez le README dans `base/RyzenMasterMonitoringDLL/`
- Vérifiez que votre CPU AMD est supporté (voir `Monitor.cpp`)
