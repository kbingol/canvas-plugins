# Sorun giderme

## Canvas bağlantısı kurulamıyor

Canvas'ın aynı bilgisayarda açık olduğunu ve **Ayarlar → MCP bağlantısı** bölümünde bağlantının açık göründüğünü kontrol edin. Ardından yeni bir yerel Codex sohbeti başlatın. Bu eklenti Canvas'ı kendiliğinden başlatmaz.

Standart paketin adresi `http://127.0.0.1:47321/mcp` olmalıdır. Canvas başka bir programın bu portu kullandığını bildiriyorsa bağlantı kendiliğinden farklı porta taşınmaz; çakışmayı çözmek gerekir. `127.0.0.1` her zaman istemcinin çalıştığı bilgisayarı gösterir; başka bir makinede çalışan oturum bu Canvas'a ulaşamaz.

## Canvas adresi farklı

Eski Canvas profilleri, örneğin `http://127.0.0.1:51098/mcp` gibi başka bir adresi koruyabilir. Mevcut adresi ve diğer istemcilerin ayarlarını değiştirmeden bağlanabilirsiniz:

1. Canvas'ta **Kopyala** ile gerçek bağlantı adresinizi alın.
2. Codex'te **Ayarlar → MCP sunucuları → Sunucu ekle** bölümünde `canvas-local` adlı bir **Streamable HTTP** bağlantısı oluşturup bu adresi yapıştırın. Alternatif olarak terminalde, aşağıdaki örneğin URL'sini kendi adresinizle değiştirerek çalıştırın:

   ```powershell
   codex mcp add canvas-local --url http://127.0.0.1:51098/mcp
   ```

3. Kurulu Canvas eklentisinin 47321 adresine ikinci bir bağlantı denemesini önlemek için `%USERPROFILE%\.codex\config.toml` dosyanızda aşağıdaki bölümü ekleyin veya mevcut aynı bölümde `enabled` değerini değiştirin:

   ```toml
   [plugins."canvas@canvas-plugins".mcp_servers.canvas]
   enabled = false
   ```

4. İstemciyi yeniden başlatıp yeni bir yerel sohbet açın. Eklentinin kullanım talimatları kalır; araçlar `canvas-local` bağlantısı üzerinden gelir.

Mevcut `canvas-local` kaydınız varsa yeni bir kayıt eklemek yerine önce adresini kontrol edin. `config.toml` dosyanızı bütünüyle değiştirmeyin ve aynı TOML bölümünü iki kez oluşturmayın. Yalnızca bu eklentinin sunucusunu kapatın; eklentinin tamamını kapatmanız gerekmez. Kurulu eklenti önbelleğindeki `mcp.json` dosyasını düzenlemeyin; paket yenilendiğinde bu değişiklik kaybolabilir.

Bu yöntem OpenAI'nin [doğrudan MCP kurulumu ve eklenti sunucusu ayarlarını](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) kullanır. Eklenti politikası için belgelenmiş bir URL değiştirme alanı varsaymaz.

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

Eklentiler ekranından Canvas'ı kaldırın veya `codex plugin remove canvas@canvas-plugins` kullanın. Pazar yeri kaynağını da kaldırmak isterseniz `codex plugin marketplace remove canvas-plugins` çalıştırın. Bunlar Canvas projelerinizi silmez ve Canvas'ın MCP tercihini değiştirmez.

Farklı adres için ayrıca `canvas-local` bağlantısı eklediyseniz, onu MCP ayarlarından veya `codex mcp remove canvas-local` ile ayrı kaldırın. [Resmî yaşam döngüsü komutları](https://learn.chatgpt.com/docs/developer-commands)
