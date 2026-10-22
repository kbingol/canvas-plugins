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

## Kaldırma

Eklentiler ekranından Canvas'ı kaldırın veya `codex plugin remove canvas@canvas-plugins` kullanın. Pazar yeri kaynağını da kaldırmak isterseniz `codex plugin marketplace remove canvas-plugins` çalıştırın. Bunlar Canvas projelerinizi silmez ve Canvas'ın MCP tercihini değiştirmez. [Resmî yaşam döngüsü komutları](https://learn.chatgpt.com/docs/developer-commands)
