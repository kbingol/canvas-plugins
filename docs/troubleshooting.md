# Sorun giderme

## Canvas bağlantısı kurulamıyor

Canvas'ın aynı bilgisayarda açık olduğunu ve **Ayarlar → MCP bağlantısı** bölümünde bağlantının açık göründüğünü kontrol edin. Ardından yeni bir yerel Codex sohbeti başlatın. Bu eklenti Canvas'ı kendiliğinden başlatmaz.

**Güncel Canvas gereklidir.** Canvas ve eklenti aynı sabit `http://127.0.0.1:47321/mcp` adresini kullanır. Eklentiyi kurmak çalışan Canvas sürümünü güncellemez; güncelleme yaptıysanız Canvas'ı yeniden açın. Adres yapıştırmanız veya config düzenlemeniz gerekmez.

Canvas başka bir programın standart portu kullandığını bildiriyorsa o programın çakışmasını çözün. Eklenti kendiliğinden farklı porta veya başka bir uygulamaya bağlanmaz. `127.0.0.1` her zaman istemcinin çalıştığı bilgisayarı gösterir; başka bir makinede çalışan oturum bu Canvas'a ulaşamaz.

## Eklenti görünmüyor veya araçlar gelmiyor

Pazar yeri adresinin `https://github.com/kbingol/canvas-plugins` olduğunu, Canvas eklentisinin yüklü ve etkin olduğunu kontrol edin. Kurulumdan önce açılmış sohbet yerine yeni bir yerel sohbet kullanın. CLI'da `/plugins` ile eklentiyi, `/mcp verbose` ile bağlantı durumunu inceleyebilirsiniz. [Resmî komut rehberi](https://learn.chatgpt.com/docs/developer-commands)

Git pazar yeri kaynağını elle yenilemek için:

```powershell
codex plugin marketplace upgrade canvas-plugins
codex plugin list
```

Bu komut katalog kaynağını yeniler. Eklentinin kurulu sürümünü ayrıca kontrol edin; otomatik güncelleme yapıldığını varsaymayın. [Pazar yeri komutları](https://developers.openai.com/plugins/build/plugins#add-a-marketplace-from-the-cli)

## Proje listesi boş

Önce Canvas'ta bir proje açın. Araçlar yalnızca çalışan uygulamadaki açık proje oturumlarını okur; diskteki bütün `.flow` dosyalarını taramaz. Projeyi kapatıp yeniden açtıysanız yeni oturum kimliğini almak için proje listesini tekrar isteyin.

## Asistan oluşturma veya dışarı aktarma araçları yok

Bu işlemler için hem Canvas eklentisi 1.2.0 veya üzeri hem de asistan oluşturma araçlarını sunan güncel Canvas uygulaması gerekir. `canvas_get_assistant`, `canvas_create_assistant` ve `canvas_export_assistant` araçlarının görünmesini kontrol edin. Eklentiyi güncellemek çalışan Canvas uygulamasına yeni araç eklemez; yeni uygulama sürümünü açıp MCP bağlantısını yenileyin. Yeni araçlar gelene kadar proje okuma işlemleri çalışabilir. Profil klasörüne elle yazarak veya kurulu eklenti cache'ini değiştirerek bağlantıyı aşmaya çalışmayın.

## Kişisel asistan silinemiyor

Kişisel paket silme için eklenti 1.3.0 ve `canvas_delete_assistant` aracını sunan güncel Canvas gerekir. `canvas_list_agents` sonucunda `origin: "personal"` ve `canDelete: true` olmalıdır; MCP ile oluşturulan paketler de kişiseldir. Hazır paketler `assistant_protected` ile korunur. `assistant_not_found`, paketin zaten kaldırılmış veya kimliğin yanlış olabileceğini gösterir; listeyi yenileyin. Silme dışarı aktarılan `.flowast` dosyalarını, proje node'larını, çıktıları ve başlamış işleri kaldırmaz.

## Asistan kimliği veya dışarı aktarma dosyası zaten var

Oluşturma mevcut paketi değiştirmez. Farklı bir asistan oluşturuyorsanız yeni, benzersiz bir `id` ve `pluginId` kullanın; mevcut asistanı güncellemek için henüz MCP aracı yoktur. Dışarı aktarmada dosya yolunu belirtmezseniz Canvas `Exports` klasöründe benzersiz bir ad seçer. Belirli bir dosya istiyorsanız mevcut dosyayı ezmeyen, mutlak bir `.flowast` yolu verin. Hata veya bağlantı kopmasından sonra aynı yazma çağrısını tekrarlamadan önce işlemin tamamlanıp tamamlanmadığını kontrol edin.

## Kaldırma

Eklentiler ekranından Canvas'ı kaldırın veya `codex plugin remove canvas@canvas-plugins` kullanın. Pazar yeri kaynağını da kaldırmak isterseniz `codex plugin marketplace remove canvas-plugins` çalıştırın. Bunlar Canvas projelerinizi silmez ve Canvas'ın MCP tercihini değiştirmez. [Resmî yaşam döngüsü komutları](https://learn.chatgpt.com/docs/developer-commands)
